from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from twick_hub.infrastructure.downloads.hls import HlsSegment
from twick_hub.infrastructure.downloads.progress_tracker import ProgressTracker
from twick_hub.infrastructure.downloads.retry_policy import RetryPolicy
from twick_hub.infrastructure.downloads.segment_manager import (
    DownloadCancelledError,
    SegmentDownloadError,
    SegmentManager,
)


class FakeSegmentFetcher:
    """``url -> bytes`` for a normal fetch, or ``url -> list[Exception |
    bytes]`` to script N failures before an eventual success (or before
    exhausting retries, if the list is all exceptions)."""

    def __init__(self, scripted: dict[str, bytes | list[Exception | bytes]]) -> None:
        self._scripted = scripted
        self.calls: list[str] = []

    async def fetch(self, url: str) -> bytes:
        self.calls.append(url)
        value = self._scripted[url]
        if isinstance(value, bytes):
            return value
        step = value.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


async def _instant_sleep(seconds: float) -> None:
    return None


def _segments(n: int, base: str = "https://cdn.example/live/") -> list[HlsSegment]:
    return [HlsSegment(sequence=i, url=f"{base}seg{i}.ts", duration_seconds=10.0) for i in range(n)]


def _manager(fetcher: FakeSegmentFetcher, **kwargs) -> SegmentManager:
    return SegmentManager(
        fetcher=fetcher,
        retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=0.01, max_delay_seconds=0.01),
        progress=ProgressTracker(),
        sleep=_instant_sleep,
        **kwargs,
    )


async def test_downloads_all_segments_successfully(tmp_path: Path):
    segments = _segments(3)
    fetcher = FakeSegmentFetcher({s.url: f"data-{s.sequence}".encode() for s in segments})
    manager = _manager(fetcher)
    manager.progress.start("job-1", total_segments=len(segments))  # normally DownloadExecutor's job

    paths = await manager.download_all("job-1", segments, tmp_path)

    assert [p.name for p in paths] == ["000000.ts", "000001.ts", "000002.ts"]
    assert (tmp_path / "000001.ts").read_bytes() == b"data-1"
    assert manager.progress.progress_of("job-1") == pytest.approx(100.0)


async def test_retries_transient_failure_then_succeeds(tmp_path: Path):
    segment = HlsSegment(sequence=0, url="https://cdn.example/seg0.ts", duration_seconds=10.0)
    fetcher = FakeSegmentFetcher({segment.url: [ConnectionError("boom"), b"ok-data"]})
    manager = _manager(fetcher)

    paths = await manager.download_all("job-1", [segment], tmp_path)

    assert paths[0].read_bytes() == b"ok-data"
    assert len(fetcher.calls) == 2


async def test_raises_after_exhausting_retries(tmp_path: Path):
    segment = HlsSegment(sequence=0, url="https://cdn.example/seg0.ts", duration_seconds=10.0)
    fetcher = FakeSegmentFetcher(
        {segment.url: [ConnectionError("1"), ConnectionError("2"), ConnectionError("3")]}
    )
    manager = _manager(fetcher)

    with pytest.raises(SegmentDownloadError) as exc_info:
        await manager.download_all("job-1", [segment], tmp_path)

    assert exc_info.value.segment == segment
    assert exc_info.value.attempts == 3
    assert len(fetcher.calls) == 3


async def test_cancellation_raises_before_fetching(tmp_path: Path):
    segments = _segments(2)
    fetcher = FakeSegmentFetcher({s.url: b"data" for s in segments})
    manager = _manager(fetcher)

    with pytest.raises(DownloadCancelledError):
        await manager.download_all("job-1", segments, tmp_path, is_cancelled=lambda: True)

    assert fetcher.calls == []


async def test_pause_blocks_until_resumed(tmp_path: Path):
    segment = HlsSegment(sequence=0, url="https://cdn.example/seg0.ts", duration_seconds=10.0)
    fetcher = FakeSegmentFetcher({segment.url: b"data"})
    manager = _manager(fetcher, pause_poll_interval_seconds=0.001)

    paused = True

    async def sleep_then_resume(seconds: float) -> None:
        nonlocal paused
        paused = False  # resume after the first pause-poll tick

    manager.sleep = sleep_then_resume

    paths = await manager.download_all("job-1", [segment], tmp_path, is_paused=lambda: paused)

    assert paths[0].exists()


async def test_cancel_while_paused_raises_instead_of_hanging(tmp_path: Path):
    segment = HlsSegment(sequence=0, url="https://cdn.example/seg0.ts", duration_seconds=10.0)
    fetcher = FakeSegmentFetcher({segment.url: b"data"})
    manager = _manager(fetcher, pause_poll_interval_seconds=0.001)

    async def fake_sleep(seconds: float) -> None:
        return None

    manager.sleep = fake_sleep

    with pytest.raises(DownloadCancelledError):
        await manager.download_all(
            "job-1", [segment], tmp_path, is_cancelled=lambda: True, is_paused=lambda: True
        )


async def test_resume_skips_already_downloaded_segments(tmp_path: Path):
    segments = _segments(2)
    (tmp_path / "000000.ts").write_bytes(b"already-here")
    fetcher = FakeSegmentFetcher({segments[1].url: b"fresh-data"})  # segment 0 never scripted
    manager = _manager(fetcher)

    await manager.download_all("job-1", segments, tmp_path)

    assert (tmp_path / "000000.ts").read_bytes() == b"already-here"
    assert (tmp_path / "000001.ts").read_bytes() == b"fresh-data"
    assert fetcher.calls == [segments[1].url]  # segment 0 was never fetched


async def test_max_concurrency_below_one_rejected():
    with pytest.raises(ValueError):
        SegmentManager(
            fetcher=FakeSegmentFetcher({}),
            retry_policy=RetryPolicy(),
            progress=ProgressTracker(),
            max_concurrency=0,
        )


async def test_concurrency_is_bounded(tmp_path: Path):
    """No thread-per-segment (Master Plan §19): with max_concurrency=2,
    never more than 2 fetches should be in flight at once."""
    segments = _segments(6)
    in_flight = 0
    max_seen = 0

    class TrackingFetcher:
        async def fetch(self, url: str) -> bytes:
            nonlocal in_flight, max_seen
            in_flight += 1
            max_seen = max(max_seen, in_flight)
            await asyncio.sleep(0)  # yield control so overlap is actually observable
            in_flight -= 1
            return b"data"

    manager = SegmentManager(
        fetcher=TrackingFetcher(),
        retry_policy=RetryPolicy(),
        progress=ProgressTracker(),
        max_concurrency=2,
        sleep=_instant_sleep,
    )

    await manager.download_all("job-1", segments, tmp_path)

    assert max_seen <= 2
