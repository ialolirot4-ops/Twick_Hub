"""Downloads a job's ``.ts`` segments with bounded concurrency (Master
Plan §19: "No crear un thread por segmento... workers limitados"),
retrying each segment per ``RetryPolicy`` and reporting progress via
``ProgressTracker``. Cancellation and pause are cooperative — checked
between attempts, not forced — the same pattern
``HlsPlaylistReader.poll_until_complete`` uses for ``should_stop``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

import httpx

from twick_hub.infrastructure.downloads.hls import HlsSegment
from twick_hub.infrastructure.downloads.progress_tracker import ProgressTracker
from twick_hub.infrastructure.downloads.retry_policy import RetryPolicy


@runtime_checkable
class SegmentFetcher(Protocol):
    async def fetch(self, url: str) -> bytes: ...


class HttpxSegmentFetcher:
    """Real ``SegmentFetcher`` — wraps the same ``httpx.AsyncClient`` the
    rest of Infrastructure already uses."""

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._http = http_client

    async def fetch(self, url: str) -> bytes:
        response = await self._http.get(url)
        response.raise_for_status()
        return response.content


class DownloadCancelledError(Exception):
    def __init__(self, job_id: str) -> None:
        super().__init__(f"download cancelled: {job_id}")
        self.job_id = job_id


class SegmentDownloadError(Exception):
    """A segment failed every attempt ``RetryPolicy`` allowed."""

    def __init__(self, segment: HlsSegment, attempts: int, cause: Exception) -> None:
        super().__init__(f"segment {segment.sequence} failed after {attempts} attempt(s): {cause}")
        self.segment = segment
        self.attempts = attempts
        self.__cause__ = cause


@dataclass
class SegmentManager:
    fetcher: SegmentFetcher
    retry_policy: RetryPolicy
    progress: ProgressTracker
    max_concurrency: int = 4
    pause_poll_interval_seconds: float = 0.5
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep

    def __post_init__(self) -> None:
        if self.max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")

    async def download_all(
        self,
        job_id: str,
        segments: list[HlsSegment],
        dest_dir: Path,
        *,
        is_cancelled: Callable[[], bool] = lambda: False,
        is_paused: Callable[[], bool] = lambda: False,
    ) -> list[Path]:
        """Downloads every segment (bounded concurrency), returns their
        local paths sorted by ``HlsSegment.sequence``. Segments already
        present on disk (same filename) are skipped — this is what makes
        resuming a paused/interrupted job idempotent: re-calling this with
        the same ``dest_dir`` only fetches what's missing.

        Does NOT call ``progress.start()`` itself — ``DownloadExecutor``
        calls that once per job (with the known total for a VOD/clip, or
        ``None`` for a live capture whose total isn't known yet) because a
        live job calls ``download_all`` repeatedly, once per
        ``HlsPlaylistReader.poll_until_complete`` batch, and re-starting
        here would reset cumulative progress on every batch."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def _bounded(segment: HlsSegment) -> Path:
            async with semaphore:
                return await self._download_one(job_id, segment, dest_dir, is_cancelled, is_paused)

        paths = await asyncio.gather(*(_bounded(segment) for segment in segments))
        return sorted(paths, key=lambda p: p.name)

    async def _download_one(
        self,
        job_id: str,
        segment: HlsSegment,
        dest_dir: Path,
        is_cancelled: Callable[[], bool],
        is_paused: Callable[[], bool],
    ) -> Path:
        path = dest_dir / f"{segment.sequence:06d}.ts"
        if path.exists():
            self.progress.advance(job_id)
            return path

        attempt = 0
        while True:
            attempt += 1
            if is_cancelled():
                raise DownloadCancelledError(job_id)
            await self._wait_while_paused(job_id, is_cancelled, is_paused)

            try:
                data = await self.fetcher.fetch(segment.url)
            except Exception as exc:  # noqa: BLE001 - any fetch failure is retryable per policy
                if not self.retry_policy.should_retry(attempt):
                    raise SegmentDownloadError(segment, attempt, exc) from exc
                await self.sleep(self.retry_policy.delay_for(attempt))
                continue

            path.write_bytes(data)
            self.progress.advance(job_id)
            return path

    async def _wait_while_paused(
        self, job_id: str, is_cancelled: Callable[[], bool], is_paused: Callable[[], bool]
    ) -> None:
        while is_paused():
            if is_cancelled():
                raise DownloadCancelledError(job_id)
            await self.sleep(self.pause_poll_interval_seconds)
