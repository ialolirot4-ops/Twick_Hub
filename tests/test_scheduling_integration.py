"""FASE 11 end to end: a real favorite with auto-download on, watched
through the FASE 10 live monitor, recorded through ``RecordingService`` and
the *real* download engine (``DownloadCoordinator`` + ``DownloadExecutor``),
finishing with a real ``DownloadFinished`` event that frees the channel
again — with only the network faked (httpx.MockTransport / a scripted
WebSocket), same approach as ``test_live_monitor_integration.py``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from tests.application.fakes import InMemoryDownloadRepository, InMemoryFavoriteRepository
from tests.application.live_monitor.fakes import collecting_bus
from tests.infrastructure.downloads.test_download_executor import (
    ScriptedHlsReader,
    WritingFakeProcessRunner,
)
from tests.infrastructure.downloads.test_segment_manager import FakeSegmentFetcher
from twick_hub.application.live_monitor.polling_monitor import PollingLiveMonitor
from twick_hub.application.live_monitor.polling_policy import PollingConfig
from twick_hub.application.live_monitor.service import LiveMonitorService
from twick_hub.application.live_monitor.tracker import LiveStateTracker
from twick_hub.application.platform_registry import PlatformAdapters, PlatformRegistry
from twick_hub.application.scheduling.auto_download import AutoDownloadService
from twick_hub.application.scheduling.destination import DestinationPlanner
from twick_hub.application.scheduling.recording import RecordingService
from twick_hub.domain.collections import Favorite
from twick_hub.domain.enums import DownloadStatus, Platform
from twick_hub.domain.events import DownloadFinished
from twick_hub.domain.value_objects import PlatformRef
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
from twick_hub.infrastructure.kick.channel_directory import KickChannelDirectory
from twick_hub.infrastructure.kick.client import KickAPIClient
from twick_hub.infrastructure.kick.livestream_batch import KickBatchLiveStatusProvider
from twick_hub.infrastructure.monitoring.process_probe import PsutilResourceProbe

CHANNEL = PlatformRef(platform=Platform.KICK, external_id="1")
_FAST = PollingConfig(base_interval=0.05, max_quiet_interval=0.05, max_backoff_interval=0.05,
                      jitter_ratio=0.0, coalesce_seconds=0.0)  # fmt: skip


async def test_a_kick_favorite_with_auto_download_is_recorded_end_to_end(tmp_path: Path):
    # --- Kick: real channel directory + batch live-status provider ---------
    is_live = {"value": False}

    def kick_handler(request: httpx.Request) -> httpx.Response:
        if "/channels" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "broadcaster_user_id": 1,
                            "slug": "streamer",
                            "stream_title": "",
                            "banner_picture": None,
                        }
                    ]
                },
            )
        ids = request.url.params.get_list("broadcaster_user_id")
        data = (
            [
                {
                    "broadcaster_user_id": 1,
                    "slug": "streamer",
                    "stream_title": "Big Stream",
                    "viewer_count": 5,
                    "started_at": "2026-09-21T10:00:00Z",
                }
            ]
            if is_live["value"] and "1" in ids
            else []
        )
        return httpx.Response(200, json={"data": data})

    kick_client = KickAPIClient(
        httpx.AsyncClient(transport=httpx.MockTransport(kick_handler)), lambda: "token"
    )
    channel_directory = KickChannelDirectory(kick_client)
    live_status = KickBatchLiveStatusProvider(kick_client)

    # --- live monitor (FASE 10) --------------------------------------------
    public_bus, events = collecting_bus()
    tracker = LiveStateTracker(public_bus)
    kick_monitor = PollingLiveMonitor(live_status, tracker, config=_FAST, label="kick")
    playback_resolver = _FakeKickPlaybackResolver()
    registry = PlatformRegistry(
        {
            Platform.KICK: PlatformAdapters(
                channel_directory=channel_directory,
                live_stream_provider=None,
                live_monitor=kick_monitor,
                playback_resolver=playback_resolver,
            )
        }
    )
    favorites = InMemoryFavoriteRepository()
    await favorites.save(Favorite(channel_ref=CHANNEL, auto_download=True, position=0))
    monitor_service = LiveMonitorService(favorites, registry, tracker, PsutilResourceProbe())

    # --- real download engine ------------------------------------------------
    downloads = InMemoryDownloadRepository()
    segment = HlsSegment(sequence=0, url="https://example.invalid/seg0.ts", duration_seconds=10.0)
    hls_reader = ScriptedHlsReader([[segment]])
    segment_manager = SegmentManager(
        fetcher=FakeSegmentFetcher({segment.url: b"tsdata"}),
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
        event_bus=public_bus,  # the executor announces DownloadFinished onto the same bus
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

    # --- recording + auto-download, wired to the one bus --------------------
    planner = DestinationPlanner(tmp_path / "rec", exists=lambda p: False)
    recorder = RecordingService(registry, tracker, downloads, engine, planner)
    recorder.attach(public_bus)
    auto_download = AutoDownloadService(favorites, recorder)
    auto_download.attach(public_bus)

    # --- run it -------------------------------------------------------------
    engine.start()
    await monitor_service.start()
    is_live["value"] = True

    for _ in range(50):
        await asyncio.sleep(0.02)
        if any(isinstance(e, DownloadFinished) for e in events):
            break

    assert kick_monitor.watched == {CHANNEL}  # sync() subscribed the auto-download favorite
    finished = [e for e in events if isinstance(e, DownloadFinished)]
    assert len(finished) == 1
    assert finished[0].status == DownloadStatus.COMPLETED
    (download,) = await downloads.list_all()
    assert download.status == DownloadStatus.COMPLETED
    destination = Path(download.destination_path)
    # The date component comes from the real wall clock (RecordingService's
    # default clock), not the test's own fixed dates — assert the rest.
    assert destination.parent == tmp_path / "rec" / "streamer"
    assert destination.name.startswith("Big Stream (") and destination.suffix == ".mp4"
    assert destination.exists()
    assert recorder.active_download_of(CHANNEL) is None  # freed once DownloadFinished arrived

    await monitor_service.stop()
    await engine.stop()
    await auto_download.wait_idle()


class _FakeKickPlaybackResolver:
    async def resolve(self, media, quality):
        from twick_hub.domain.value_objects import PlaybackSource

        return PlaybackSource(url="https://example.invalid/live.m3u8", quality_label="best")

    async def available_qualities(self, media) -> list[str]:
        return ["best"]


async def _instant_sleep(_seconds: float) -> None:
    return None
