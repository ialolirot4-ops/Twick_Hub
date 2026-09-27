"""FASE 12 end to end: ``EnqueuePlaylistDownloadUseCase`` through the *real*
download engine (``DownloadQueue`` + ``DownloadCoordinator`` +
``DownloadExecutor`` + ``JobControlStore`` + ``DownloadService``, same
components ``tests/test_scheduling_integration.py`` exercises for FASE 11),
proving a playlist item is not just "enqueued" (what the application-layer
fakes in ``tests/application/test_playlists.py`` check) but actually ends
up as a completed file on disk.

The playlist mixes a Twitch item (a platform with a registered
``PlaybackResolver``) and a Kick one (which, as of this phase, has none —
docs/architecture-decisions.md AD-05/RISK-KICK-01: Kick's VOD/clip
playback was scoped to a future ``KickUnofficialAdapter`` that hasn't been
built yet). This is deliberate: it proves ``EnqueuePlaylistDownloadUseCase``
degrades gracefully for the one platform gap that already exists in this
codebase, end to end, rather than only against a synthetic "no qualities"
fake as the application-layer tests do.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from tests.application.fakes import (
    FakeChannelDirectory,
    InMemoryDownloadRepository,
    InMemoryPlaylistRepository,
    make_channel,
)
from tests.infrastructure.downloads.test_download_executor import (
    ScriptedHlsReader,
    WritingFakeProcessRunner,
)
from tests.infrastructure.downloads.test_segment_manager import FakeSegmentFetcher
from twick_hub.application.platform_registry import PlatformAdapters, PlatformRegistry
from twick_hub.application.playlists import (
    AddMediaToPlaylistUseCase,
    CreatePlaylistUseCase,
    EnqueuePlaylistDownloadUseCase,
)
from twick_hub.application.scheduling.destination import DestinationPlanner
from twick_hub.domain.enums import DownloadStatus, MediaKind, Platform
from twick_hub.domain.value_objects import Media, PlatformRef
from twick_hub.infrastructure.downloads.download_coordinator import DownloadCoordinator
from twick_hub.infrastructure.downloads.download_executor import DownloadExecutor
from twick_hub.infrastructure.downloads.download_queue import DownloadQueue
from twick_hub.infrastructure.downloads.download_service import DownloadService, JobControlStore
from twick_hub.infrastructure.downloads.ffmpeg_processor import FFmpegProcessor
from twick_hub.infrastructure.downloads.hls import HlsSegment
from twick_hub.infrastructure.downloads.media_processor import MediaProcessor
from twick_hub.infrastructure.downloads.progress_tracker import ProgressTracker
from twick_hub.infrastructure.downloads.retry_policy import RetryPolicy
from twick_hub.infrastructure.downloads.segment_manager import SegmentManager

_TWITCH_CHANNEL = PlatformRef(platform=Platform.TWITCH, external_id="chan1")
_TWITCH_VIDEO = Media(
    kind=MediaKind.VIDEO,
    ref=PlatformRef(platform=Platform.TWITCH, external_id="v1"),
    title="A Twitch VOD",
    channel_ref=_TWITCH_CHANNEL,
)
_KICK_CLIP = Media(
    kind=MediaKind.CLIP,
    ref=PlatformRef(platform=Platform.KICK, external_id="c1"),
    title="A Kick clip",
    channel_ref=PlatformRef(platform=Platform.KICK, external_id="chan2"),
)


class _FakeTwitchPlaybackResolver:
    """Stands in for the real ``TwitchPlaybackResolver`` (already tested on
    its own, tests/infrastructure/twitch/playback/test_playback_resolver.py)
    so this module can focus on the playlist→engine wiring — same "fake the
    one already-proven adapter, keep the download engine real" split as
    ``tests/test_scheduling_integration.py``."""

    async def resolve(self, media, quality):
        from twick_hub.domain.value_objects import PlaybackSource

        return PlaybackSource(url="https://example.invalid/vod.m3u8", quality_label=quality)

    async def available_qualities(self, media) -> list[str]:
        return ["1080p60", "720p60"]


async def test_a_mixed_platform_playlist_downloads_the_covered_item_and_reports_the_gap(
    tmp_path: Path,
):
    # --- registry: Twitch has a resolver, Kick does not (AD-05) -------------
    directory = FakeChannelDirectory()
    directory.add(make_channel("chan1", "streamer", Platform.TWITCH))
    registry = PlatformRegistry(
        {
            Platform.TWITCH: PlatformAdapters(
                channel_directory=directory, playback_resolver=_FakeTwitchPlaybackResolver()
            ),
            Platform.KICK: PlatformAdapters(),  # no playback_resolver at all
        }
    )

    downloads = InMemoryDownloadRepository()
    hls_reader = ScriptedHlsReader(
        [[HlsSegment(sequence=0, url="https://example.invalid/seg0.ts", duration_seconds=10.0)]]
    )
    segment_manager = SegmentManager(
        fetcher=FakeSegmentFetcher({"https://example.invalid/seg0.ts": b"tsdata"}),
        retry_policy=RetryPolicy(max_attempts=2, base_delay_seconds=0.01),
        progress=ProgressTracker(),
        sleep=_instant_sleep,
    )
    media_processor = MediaProcessor(ffmpeg=FFmpegProcessor(runner=WritingFakeProcessRunner()))
    executor = DownloadExecutor(
        registry=registry,
        downloads=downloads,
        hls_reader=hls_reader,
        segment_manager=segment_manager,
        media_processor=media_processor,
        work_dir=tmp_path / "work",
        poll_interval_seconds=0.01,
        sleep=_instant_sleep,
    )
    queue = DownloadQueue()
    control = JobControlStore()
    coordinator = DownloadCoordinator(
        queue,
        executor,
        worker_count=2,
        is_cancelled=control.is_cancelled,
        is_paused=control.is_paused,
    )
    engine = DownloadService(
        downloads=downloads,
        progress=ProgressTracker(),
        queue=queue,
        coordinator=coordinator,
        control=control,
    )

    # --- playlist with one item per platform --------------------------------
    playlists = InMemoryPlaylistRepository()
    playlist = await CreatePlaylistUseCase(playlists=playlists).execute("Mixed")
    playlist = await AddMediaToPlaylistUseCase(playlists=playlists).execute(
        playlist.id, _TWITCH_VIDEO
    )
    playlist = await AddMediaToPlaylistUseCase(playlists=playlists).execute(playlist.id, _KICK_CLIP)

    planner = DestinationPlanner(tmp_path / "rec", exists=lambda p: False)
    use_case = EnqueuePlaylistDownloadUseCase(
        registry=registry, playlists=playlists, downloads=downloads, engine=engine, planner=planner
    )

    # --- run it ---------------------------------------------------------
    engine.start()
    report = await use_case.execute(playlist.id)

    assert len(report.enqueued) == 1  # only the Twitch item
    assert len(report.failed) == 1
    failed_item_id, reason = report.failed[0]
    assert failed_item_id == playlist.items[1].id  # the Kick clip
    assert "no playable qualities" in reason

    for _ in range(50):
        await asyncio.sleep(0.02)
        stored = await downloads.get(report.enqueued[0].id)
        if stored is not None and stored.status in (
            DownloadStatus.COMPLETED,
            DownloadStatus.FAILED,
        ):
            break

    stored = await downloads.get(report.enqueued[0].id)
    assert stored is not None
    assert stored.status == DownloadStatus.COMPLETED
    assert Path(stored.destination_path).exists()
    assert Path(stored.destination_path).parent == tmp_path / "rec" / "streamer"

    await engine.stop()


async def _instant_sleep(_seconds: float) -> None:
    return None
