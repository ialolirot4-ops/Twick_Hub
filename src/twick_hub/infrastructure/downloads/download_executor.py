"""Drives ONE ``Download`` through the full pipeline (Master Plan §17):
Platform → Playback → Manifest/M3U8 → quality selection → segments →
concurrent download → retry/recovery → FFmpeg → final file.

Quality *selection* already happened at enqueue time
(``EnqueueDownloadUseCase``, FASE 3); this re-resolves playback right
before downloading because Twitch's playback tokens are short-lived
(FASE 4c) — the URL from enqueue time may already be stale by the time a
worker picks the job up.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

from twick_hub.application.platform_registry import PlatformRegistry
from twick_hub.domain.downloads import Download
from twick_hub.domain.enums import DownloadStatus
from twick_hub.domain.protocols import DownloadRepository
from twick_hub.infrastructure.downloads.hls import HlsSegment
from twick_hub.infrastructure.downloads.media_processor import MediaProcessor
from twick_hub.infrastructure.downloads.segment_manager import (
    DownloadCancelledError,
    SegmentDownloadError,
    SegmentManager,
)


@runtime_checkable
class HlsReader(Protocol):
    """What ``DownloadExecutor`` needs from ``HlsPlaylistReader``
    (infrastructure/downloads/hls.py) — a Protocol, not that concrete
    class, so tests can substitute a scripted fake the same way
    ``SegmentManager`` substitutes ``SegmentFetcher``."""

    def poll_until_complete(
        self,
        playlist_url: str,
        *,
        poll_interval_seconds: float,
        sleep: Callable[[float], Awaitable[None]],
        should_stop: Callable[[], bool] | None = None,
    ) -> AsyncIterator[list[HlsSegment]]: ...


class DownloadExecutor:
    def __init__(
        self,
        registry: PlatformRegistry,
        downloads: DownloadRepository,
        hls_reader: HlsReader,
        segment_manager: SegmentManager,
        media_processor: MediaProcessor,
        work_dir: Path,
        *,
        poll_interval_seconds: float = 5.0,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._registry = registry
        self._downloads = downloads
        self._hls_reader = hls_reader
        self._segment_manager = segment_manager
        self._media_processor = media_processor
        self._work_dir = work_dir
        self._poll_interval_seconds = poll_interval_seconds
        self._sleep = sleep or asyncio.sleep

    async def run(
        self,
        download_id: str,
        *,
        is_cancelled: Callable[[], bool],
        is_paused: Callable[[], bool],
    ) -> None:
        """Runs the whole pipeline for ``download_id``, persisting a
        status transition (Master Plan §44's eight states) at each stage.
        Pause is handled inside ``SegmentManager`` (the worker blocks and
        resumes in place); ``DownloadService.pause()``/``resume()`` set
        the user-visible ``Download.status`` independently, since the
        worker can be sitting blocked mid-segment when that happens.
        """
        download = await self._downloads.get(download_id)
        if download is None:
            return  # already gone (e.g. cancelled before a worker picked it up)

        download = await self._transition(download, DownloadStatus.PREPARING)

        try:
            source = await self._registry.resolve_playback(download.media, download.quality_label)
        except Exception as exc:  # noqa: BLE001 - any resolve failure fails this download, not the worker
            await self._fail(download_id, str(exc))
            return

        if is_cancelled():
            await self._transition(download, DownloadStatus.CANCELLED)
            return

        segments_dir = self._work_dir / download_id / "segments"
        # Total segment count isn't known up front for a live capture, and
        # a VOD's true total isn't known until its single batch is fully
        # read either — see docs/architecture-decisions.md's FASE 7 entry
        # for why per-segment percentage reporting is deferred rather than
        # approximated here.
        self._segment_manager.progress.start(download_id, total_segments=None)

        download = await self._transition(download, DownloadStatus.DOWNLOADING)
        downloaded_paths: list[Path] = []
        try:
            async for batch in self._hls_reader.poll_until_complete(
                source.url,
                poll_interval_seconds=self._poll_interval_seconds,
                sleep=self._sleep,
                should_stop=is_cancelled,
            ):
                new_paths = await self._segment_manager.download_all(
                    download_id, batch, segments_dir, is_cancelled=is_cancelled, is_paused=is_paused
                )
                downloaded_paths.extend(new_paths)
        except DownloadCancelledError:
            await self._transition(download, DownloadStatus.CANCELLED)
            return
        except SegmentDownloadError as exc:
            await self._fail(download_id, str(exc))
            return

        if is_cancelled():
            # The HLS poll loop can also stop early via should_stop
            # (is_cancelled) without SegmentManager ever raising — e.g.
            # cancellation lands between polls, with no segment in
            # flight. Must still report CANCELLED, not silently proceed
            # to finalize whatever partial content was downloaded.
            await self._transition(download, DownloadStatus.CANCELLED)
            return

        download = await self._transition(download, DownloadStatus.PROCESSING)

        output_path = Path(download.destination_path)
        try:
            ordered_paths = sorted(downloaded_paths, key=lambda p: p.name)
            await self._media_processor.finalize(ordered_paths, output_path)
        except Exception as exc:  # noqa: BLE001 - ffmpeg failure fails this download, not the worker
            await self._fail(download_id, str(exc))
            return

        completed = replace(
            download,
            status=DownloadStatus.COMPLETED,
            progress_percent=100.0,
            completed_at=datetime.now(),
            file_size_bytes=output_path.stat().st_size if output_path.exists() else None,
        )
        await self._downloads.save(completed)
        self._segment_manager.progress.finish(download_id)

    async def _transition(self, download: Download, status: DownloadStatus) -> Download:
        updated = replace(download, status=status)
        await self._downloads.save(updated)
        return updated

    async def _fail(self, download_id: str, message: str) -> None:
        download = await self._downloads.get(download_id)
        if download is None:
            return
        updated = replace(download, status=DownloadStatus.FAILED, error_message=message)
        await self._downloads.save(updated)
        self._segment_manager.progress.finish(download_id)
