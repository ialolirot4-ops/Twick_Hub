from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

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
