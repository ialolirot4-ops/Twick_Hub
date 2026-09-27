from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from tests.application.fakes import FakePlaybackResolver, InMemoryDownloadRepository
from tests.infrastructure.downloads.test_segment_manager import FakeSegmentFetcher
from twick_hub.application.platform_registry import PlatformAdapters, PlatformRegistry
from twick_hub.domain.downloads import Download
from twick_hub.domain.enums import DownloadStatus, MediaKind, Platform
from twick_hub.domain.value_objects import Media, PlatformRef
from twick_hub.infrastructure.downloads.download_executor import DownloadExecutor
from twick_hub.infrastructure.downloads.ffmpeg_processor import FFmpegProcessor, ProcessResult
from twick_hub.infrastructure.downloads.hls import HlsSegment
from twick_hub.infrastructure.downloads.media_processor import MediaProcessor
from twick_hub.infrastructure.downloads.progress_tracker import ProgressTracker
from twick_hub.infrastructure.downloads.retry_policy import RetryPolicy
from twick_hub.infrastructure.downloads.segment_manager import SegmentManager


class ScriptedHlsReader:
    """Stands in for HlsPlaylistReader (already tested on its own,
    test_hls.py) so this module can focus purely on DownloadExecutor's
    orchestration — one batch per poll, in the order given."""

    def __init__(self, batches: list[list[HlsSegment]]) -> None:
        self._batches = batches
        self.read_urls: list[str] = []

    async def poll_until_complete(
        self, playlist_url: str, *, poll_interval_seconds: float, sleep, should_stop=None
    ) -> AsyncIterator[list[HlsSegment]]:
        self.read_urls.append(playlist_url)
        for batch in self._batches:
            if should_stop is not None and should_stop():
                return
            yield batch


class RaisingPlaybackResolver:
    async def resolve(self, media: Media, quality: str):
        raise RuntimeError("playback token request failed")

    async def available_qualities(self, media: Media) -> list[str]:
        return []


class WritingFakeProcessRunner:
    """Like FakeProcessRunner, but actually writes bytes to the ffmpeg
    output path on success — needed here because DownloadExecutor calls
    ``output_path.stat().st_size`` after a successful finalize()."""

    def __init__(self, returncode: int = 0, stderr: str = "") -> None:
        self.returncode = returncode
        self.stderr = stderr
        self.calls: list[list[str]] = []

    async def run(self, argv: list[str], *, timeout_seconds: float | None) -> ProcessResult:
        self.calls.append(argv)
        if self.returncode == 0:
            Path(argv[-1]).write_bytes(b"final remuxed video bytes")
        return ProcessResult(returncode=self.returncode, stderr=self.stderr)


async def _instant_sleep(seconds: float) -> None:
    return None


def _media() -> Media:
    ref = PlatformRef(platform=Platform.TWITCH, external_id="v1")
    return Media(kind=MediaKind.VIDEO, ref=ref, title="A VOD")


def _download(tmp_path: Path) -> Download:
    return Download(
        media=_media(), destination_path=str(tmp_path / "final.mp4"), quality_label="source"
    )


def _executor(
    tmp_path: Path,
    *,
    downloads: InMemoryDownloadRepository,
    playback_resolver=None,
    hls_reader: ScriptedHlsReader,
    fetcher_map: dict[str, bytes | list[Exception | bytes]] | None = None,
    process_runner=None,
    retry_policy: RetryPolicy | None = None,
) -> DownloadExecutor:
    resolver = playback_resolver or FakePlaybackResolver()
    registry = PlatformRegistry({Platform.TWITCH: PlatformAdapters(playback_resolver=resolver)})
    fetcher = FakeSegmentFetcher(fetcher_map or {})
    policy = retry_policy or RetryPolicy(
        max_attempts=2, base_delay_seconds=0.01, max_delay_seconds=0.01
    )
    segment_manager = SegmentManager(
        fetcher=fetcher, retry_policy=policy, progress=ProgressTracker(), sleep=_instant_sleep
    )
    media_processor = MediaProcessor(
        ffmpeg=FFmpegProcessor(runner=process_runner or WritingFakeProcessRunner())
    )
    return DownloadExecutor(
        registry=registry,
        downloads=downloads,
        hls_reader=hls_reader,
        segment_manager=segment_manager,
        media_processor=media_processor,
        work_dir=tmp_path / "work",
        poll_interval_seconds=0.01,
        sleep=_instant_sleep,
    )


async def test_successful_vod_download_completes(tmp_path: Path):
    downloads = InMemoryDownloadRepository()
    download = _download(tmp_path)
    await downloads.save(download)

    segments = [
        HlsSegment(sequence=0, url="https://example.invalid/v1/seg0.ts", duration_seconds=10.0),
        HlsSegment(sequence=1, url="https://example.invalid/v1/seg1.ts", duration_seconds=10.0),
    ]
    hls_reader = ScriptedHlsReader([segments])
    fetcher_map: dict[str, bytes | list[Exception | bytes]] = {s.url: b"tsdata" for s in segments}
    executor = _executor(
        tmp_path, downloads=downloads, hls_reader=hls_reader, fetcher_map=fetcher_map
    )

    await executor.run(download.id, is_cancelled=lambda: False, is_paused=lambda: False)

    final = await downloads.get(download.id)
    assert final is not None
    assert final.status == DownloadStatus.COMPLETED
    assert final.progress_percent == 100.0
    assert final.file_size_bytes == len(b"final remuxed video bytes")
    assert final.completed_at is not None
    assert Path(download.destination_path).exists()


async def test_unknown_download_id_is_a_noop(tmp_path: Path):
    downloads = InMemoryDownloadRepository()
    executor = _executor(tmp_path, downloads=downloads, hls_reader=ScriptedHlsReader([]))

    await executor.run("does-not-exist", is_cancelled=lambda: False, is_paused=lambda: False)
    # no exception, and nothing to assert in the (empty) repository


async def test_resolve_playback_failure_marks_failed(tmp_path: Path):
    downloads = InMemoryDownloadRepository()
    download = _download(tmp_path)
    await downloads.save(download)
    executor = _executor(
        tmp_path,
        downloads=downloads,
        playback_resolver=RaisingPlaybackResolver(),
        hls_reader=ScriptedHlsReader([]),
    )

    await executor.run(download.id, is_cancelled=lambda: False, is_paused=lambda: False)

    final = await downloads.get(download.id)
    assert final is not None
    assert final.status == DownloadStatus.FAILED
    assert final.error_message is not None
    assert "playback token request failed" in final.error_message


async def test_cancelled_immediately_after_playback_resolves(tmp_path: Path):
    downloads = InMemoryDownloadRepository()
    download = _download(tmp_path)
    await downloads.save(download)
    executor = _executor(tmp_path, downloads=downloads, hls_reader=ScriptedHlsReader([]))

    await executor.run(download.id, is_cancelled=lambda: True, is_paused=lambda: False)

    final = await downloads.get(download.id)
    assert final is not None
    assert final.status == DownloadStatus.CANCELLED


async def test_cancellation_mid_download_stops_the_pipeline(tmp_path: Path):
    downloads = InMemoryDownloadRepository()
    download = _download(tmp_path)
    await downloads.save(download)

    url = "https://example.invalid/seg0.ts"
    segments = [HlsSegment(sequence=0, url=url, duration_seconds=10.0)]
    hls_reader = ScriptedHlsReader([segments])
    fetcher_map: dict[str, bytes | list[Exception | bytes]] = {s.url: b"data" for s in segments}
    executor = _executor(
        tmp_path, downloads=downloads, hls_reader=hls_reader, fetcher_map=fetcher_map
    )

    calls = {"n": 0}

    def is_cancelled() -> bool:
        calls["n"] += 1
        return calls["n"] > 1  # false the first time (pre-loop check), true from then on

    await executor.run(download.id, is_cancelled=is_cancelled, is_paused=lambda: False)

    final = await downloads.get(download.id)
    assert final is not None
    assert final.status == DownloadStatus.CANCELLED


async def test_segment_failure_exhausting_retries_marks_failed(tmp_path: Path):
    downloads = InMemoryDownloadRepository()
    download = _download(tmp_path)
    await downloads.save(download)

    segment = HlsSegment(sequence=0, url="https://example.invalid/seg0.ts", duration_seconds=10.0)
    hls_reader = ScriptedHlsReader([[segment]])
    fetcher = FakeSegmentFetcher(
        {segment.url: [ConnectionError("down"), ConnectionError("still down")]}
    )

    registry = PlatformRegistry(
        {Platform.TWITCH: PlatformAdapters(playback_resolver=FakePlaybackResolver())}
    )
    segment_manager = SegmentManager(
        fetcher=fetcher,
        retry_policy=RetryPolicy(max_attempts=2, base_delay_seconds=0.01),
        progress=ProgressTracker(),
        sleep=_instant_sleep,
    )
    executor = DownloadExecutor(
        registry=registry,
        downloads=downloads,
        hls_reader=hls_reader,
        segment_manager=segment_manager,
        media_processor=MediaProcessor(ffmpeg=FFmpegProcessor(runner=WritingFakeProcessRunner())),
        work_dir=tmp_path / "work",
        sleep=_instant_sleep,
    )

    await executor.run(download.id, is_cancelled=lambda: False, is_paused=lambda: False)

    final = await downloads.get(download.id)
    assert final is not None
    assert final.status == DownloadStatus.FAILED
    assert final.error_message is not None
    assert "seg" in final.error_message or "segment" in final.error_message.lower()


async def test_ffmpeg_failure_marks_failed(tmp_path: Path):
    downloads = InMemoryDownloadRepository()
    download = _download(tmp_path)
    await downloads.save(download)

    segment = HlsSegment(sequence=0, url="https://example.invalid/seg0.ts", duration_seconds=10.0)
    hls_reader = ScriptedHlsReader([[segment]])
    failing_runner = WritingFakeProcessRunner(returncode=1, stderr="moov atom not found")
    executor = _executor(
        tmp_path,
        downloads=downloads,
        hls_reader=hls_reader,
        fetcher_map={segment.url: b"data"},
        process_runner=failing_runner,
    )

    await executor.run(download.id, is_cancelled=lambda: False, is_paused=lambda: False)

    final = await downloads.get(download.id)
    assert final is not None
    assert final.status == DownloadStatus.FAILED
    assert final.error_message is not None
    assert "moov atom not found" in final.error_message
    assert not Path(download.destination_path).exists()


async def test_live_capture_downloads_across_multiple_poll_batches(tmp_path: Path):
    downloads = InMemoryDownloadRepository()
    download = _download(tmp_path)
    await downloads.save(download)

    batch1 = [HlsSegment(sequence=0, url="https://example.invalid/seg0.ts", duration_seconds=10.0)]
    batch2 = [HlsSegment(sequence=1, url="https://example.invalid/seg1.ts", duration_seconds=10.0)]
    hls_reader = ScriptedHlsReader([batch1, batch2])
    fetcher_map: dict[str, bytes | list[Exception | bytes]] = {
        "https://example.invalid/seg0.ts": b"a",
        "https://example.invalid/seg1.ts": b"b",
    }
    runner = WritingFakeProcessRunner()
    executor = _executor(
        tmp_path,
        downloads=downloads,
        hls_reader=hls_reader,
        fetcher_map=fetcher_map,
        process_runner=runner,
    )

    await executor.run(download.id, is_cancelled=lambda: False, is_paused=lambda: False)

    final = await downloads.get(download.id)
    assert final is not None
    assert final.status == DownloadStatus.COMPLETED
    # both segments, across both batches, made it into the ffmpeg concat list —
    # the concat list itself is cleaned up by the time we get here, so assert
    # indirectly: two distinct segment files were written to the segments dir.
    segments_dir = tmp_path / "work" / download.id / "segments"
    assert sorted(p.name for p in segments_dir.glob("*.ts")) == ["000000.ts", "000001.ts"]


async def test_paused_worker_blocks_then_completes_once_resumed(tmp_path: Path):
    downloads = InMemoryDownloadRepository()
    download = _download(tmp_path)
    await downloads.save(download)

    segment = HlsSegment(sequence=0, url="https://example.invalid/seg0.ts", duration_seconds=10.0)
    hls_reader = ScriptedHlsReader([[segment]])
    executor = _executor(
        tmp_path, downloads=downloads, hls_reader=hls_reader, fetcher_map={segment.url: b"data"}
    )

    paused = True

    async def resume_after_one_tick(seconds: float) -> None:
        nonlocal paused
        paused = False

    executor._segment_manager.sleep = resume_after_one_tick  # noqa: SLF001 - test-only override

    await executor.run(download.id, is_cancelled=lambda: False, is_paused=lambda: paused)

    final = await downloads.get(download.id)
    assert final is not None
    assert final.status == DownloadStatus.COMPLETED


# --- FASE 11: DownloadFinished announcement ----------------------------------


async def test_a_completed_download_announces_download_finished(tmp_path: Path):
    from twick_hub.domain.events import DownloadFinished, EventBus

    downloads = InMemoryDownloadRepository()
    download = _download(tmp_path)
    await downloads.save(download)
    segments = [
        HlsSegment(sequence=0, url="https://example.invalid/seg0.ts", duration_seconds=10.0)
    ]
    hls_reader = ScriptedHlsReader([segments])
    bus = EventBus()
    seen = []
    bus.subscribe(seen.append)
    executor = _executor(
        tmp_path,
        downloads=downloads,
        hls_reader=hls_reader,
        fetcher_map={segments[0].url: b"data"},
    )
    executor._event_bus = bus  # type: ignore[attr-defined]

    await executor.run(download.id, is_cancelled=lambda: False, is_paused=lambda: False)

    assert seen == [DownloadFinished(download.id, DownloadStatus.COMPLETED, None)]


async def test_a_failed_download_announces_download_finished_with_the_error(tmp_path: Path):
    from twick_hub.domain.events import EventBus

    downloads = InMemoryDownloadRepository()
    download = _download(tmp_path)
    await downloads.save(download)
    segment = HlsSegment(sequence=0, url="https://example.invalid/seg0.ts", duration_seconds=10.0)
    hls_reader = ScriptedHlsReader([[segment]])
    bus = EventBus()
    seen = []
    bus.subscribe(seen.append)
    executor = _executor(
        tmp_path,
        downloads=downloads,
        hls_reader=hls_reader,
        fetcher_map={segment.url: [ConnectionError("down"), ConnectionError("still down")]},
    )
    executor._event_bus = bus  # type: ignore[attr-defined]

    await executor.run(download.id, is_cancelled=lambda: False, is_paused=lambda: False)

    assert len(seen) == 1
    assert seen[0].download_id == download.id
    assert seen[0].status == DownloadStatus.FAILED
    assert seen[0].error_message is not None


async def test_a_cancelled_download_announces_download_finished(tmp_path: Path):
    from twick_hub.domain.events import DownloadFinished, EventBus

    downloads = InMemoryDownloadRepository()
    download = _download(tmp_path)
    await downloads.save(download)
    segments = [
        HlsSegment(sequence=0, url="https://example.invalid/s0.ts", duration_seconds=10.0),
        HlsSegment(sequence=1, url="https://example.invalid/s1.ts", duration_seconds=10.0),
    ]
    hls_reader = ScriptedHlsReader([[segments[0]], [segments[1]]])
    bus = EventBus()
    seen = []
    bus.subscribe(seen.append)
    executor = _executor(
        tmp_path,
        downloads=downloads,
        hls_reader=hls_reader,
        fetcher_map={s.url: b"data" for s in segments},
    )
    executor._event_bus = bus  # type: ignore[attr-defined]
    calls = [0]

    def is_cancelled() -> bool:
        calls[0] += 1
        return calls[0] > 1

    await executor.run(download.id, is_cancelled=is_cancelled, is_paused=lambda: False)

    assert seen == [DownloadFinished(download.id, DownloadStatus.CANCELLED, None)]


async def test_no_event_bus_means_no_announcement_and_no_error(tmp_path: Path):
    downloads = InMemoryDownloadRepository()
    download = _download(tmp_path)
    await downloads.save(download)
    segments = [
        HlsSegment(sequence=0, url="https://example.invalid/seg0.ts", duration_seconds=10.0)
    ]
    executor = _executor(
        tmp_path,
        downloads=downloads,
        hls_reader=ScriptedHlsReader([segments]),
        fetcher_map={segments[0].url: b"data"},
    )

    await executor.run(
        download.id, is_cancelled=lambda: False, is_paused=lambda: False
    )  # must not raise

    final = await downloads.get(download.id)
    assert final is not None and final.status == DownloadStatus.COMPLETED


async def test_an_unexpected_exception_fails_the_download_announces_it_and_still_reraises(
    tmp_path: Path,
):
    from twick_hub.domain.events import DownloadFinished, EventBus

    downloads = InMemoryDownloadRepository()
    download = _download(tmp_path)
    await downloads.save(download)

    class ExplodingHlsReader:
        async def poll_until_complete(self, *args, **kwargs):
            raise RuntimeError("totally unexpected")
            yield []  # pragma: no cover - never reached, makes this an async generator

    bus = EventBus()
    seen = []
    bus.subscribe(seen.append)
    executor = _executor(
        tmp_path,
        downloads=downloads,
        hls_reader=ExplodingHlsReader(),  # type: ignore[arg-type]
    )
    executor._event_bus = bus  # type: ignore[attr-defined]

    with pytest.raises(RuntimeError, match="totally unexpected"):
        await executor.run(download.id, is_cancelled=lambda: False, is_paused=lambda: False)

    final = await downloads.get(download.id)
    assert final is not None and final.status == DownloadStatus.FAILED
    assert seen == [DownloadFinished(download.id, DownloadStatus.FAILED, final.error_message)]


async def test_cancellation_during_run_is_not_treated_as_finished(tmp_path: Path):
    """asyncio.CancelledError means the worker itself is being torn down
    (app shutdown) — the download's status is left as-is for restart
    recovery to handle, and no DownloadFinished is announced."""
    from twick_hub.domain.events import EventBus

    downloads = InMemoryDownloadRepository()
    download = _download(tmp_path)
    await downloads.save(download)

    class HangingHlsReader:
        async def poll_until_complete(self, *args, **kwargs):
            await asyncio.sleep(3600)
            yield []  # pragma: no cover

    bus = EventBus()
    seen = []
    bus.subscribe(seen.append)
    executor = _executor(
        tmp_path,
        downloads=downloads,
        hls_reader=HangingHlsReader(),  # type: ignore[arg-type]
    )
    executor._event_bus = bus  # type: ignore[attr-defined]

    task = asyncio.create_task(
        executor.run(download.id, is_cancelled=lambda: False, is_paused=lambda: False)
    )
    await asyncio.sleep(0.05)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert seen == []


async def test_segment_manager_cancellation_mid_batch_marks_cancelled(tmp_path: Path):
    """Distinct from ``test_cancellation_mid_download_stops_the_pipeline``
    above, where cancellation is caught by the HLS reader's own
    ``should_stop`` check before any segment reaches ``SegmentManager`` at
    all. Here the batch IS handed off, and cancellation only takes effect
    once ``SegmentManager`` is already working through it — the
    ``DownloadCancelledError`` it raises has to propagate out through
    ``DownloadExecutor``'s own ``except DownloadCancelledError`` clause,
    not either of ``_run``'s own pre-loop/post-loop ``is_cancelled()``
    checks."""
    downloads = InMemoryDownloadRepository()
    download = _download(tmp_path)
    await downloads.save(download)

    segment = HlsSegment(sequence=0, url="https://example.invalid/seg0.ts", duration_seconds=10.0)
    hls_reader = ScriptedHlsReader([[segment]])
    executor = _executor(
        tmp_path, downloads=downloads, hls_reader=hls_reader, fetcher_map={segment.url: b"data"}
    )

    calls = {"n": 0}

    def is_cancelled() -> bool:
        calls["n"] += 1
        # False for _run's pre-loop check and the HLS reader's should_stop
        # check; only true once SegmentManager itself asks.
        return calls["n"] > 2

    await executor.run(download.id, is_cancelled=is_cancelled, is_paused=lambda: False)

    final = await downloads.get(download.id)
    assert final is not None
    assert final.status == DownloadStatus.CANCELLED


async def test_fail_on_a_download_that_no_longer_exists_is_a_noop(tmp_path: Path):
    """Guards against a download disappearing (e.g. deleted concurrently)
    between the pipeline failing and ``_fail`` re-reading it to record the
    error — must not raise trying to update something that's gone."""
    downloads = InMemoryDownloadRepository()
    executor = _executor(tmp_path, downloads=downloads, hls_reader=ScriptedHlsReader([]))

    await executor._fail("does-not-exist", "some error")  # type: ignore[attr-defined]  # must not raise
