"""A ready-made Twitch world for the scheduling tests: one channel that can
go live and offline (through the same ``LiveStateTracker`` the FASE 10 live
monitor feeds — see recording.py's module docstring for why), a resolver
with real-looking quality labels, and an engine that just remembers what it
was asked to run."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from tests.application.fakes import (
    FakeChannelDirectory,
    FakeDownloadEngine,
    FakePlaybackResolver,
    InMemoryDownloadRepository,
    make_channel,
)
from tests.application.live_monitor.fakes import stream_of
from twick_hub.application.live_monitor.tracker import LiveStateTracker
from twick_hub.application.platform_registry import PlatformAdapters, PlatformRegistry
from twick_hub.application.scheduling.destination import DestinationPlanner
from twick_hub.application.scheduling.recording import RecordingService
from twick_hub.domain.enums import DownloadStatus, Platform
from twick_hub.domain.events import EventBus
from twick_hub.domain.value_objects import PlatformRef

NOW = datetime(2026, 9, 21, 10, 0)  # a Monday
CHANNEL = PlatformRef(platform=Platform.TWITCH, external_id="1")
OTHER = PlatformRef(platform=Platform.TWITCH, external_id="2")


class Clock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class Env:
    def __init__(self, *, template: str | None = None) -> None:
        self.clock = Clock()
        self.directory = FakeChannelDirectory()
        self.directory.add(make_channel("1", "streamer", Platform.TWITCH))
        self.directory.add(make_channel("2", "other", Platform.TWITCH))
        self.resolver = FakePlaybackResolver(qualities=["1080p60", "720p60", "audio_only"])
        self.registry = PlatformRegistry(
            {
                Platform.TWITCH: PlatformAdapters(
                    channel_directory=self.directory,
                    playback_resolver=self.resolver,
                )
            }
        )
        self.bus = EventBus()
        self.tracker = LiveStateTracker(self.bus)
        self.downloads = InMemoryDownloadRepository()
        self.engine = FakeDownloadEngine()
        planner_args = {"template": template} if template else {}
        self.planner = DestinationPlanner(Path("/rec"), exists=lambda p: False, **planner_args)
        self.recorder = RecordingService(
            self.registry, self.tracker, self.downloads, self.engine, self.planner, clock=self.clock
        )
        self.recorder.attach(self.bus)

    async def go_live(self, channel: PlatformRef = CHANNEL, *, authoritative: bool = False) -> None:
        await self.tracker.observe_live(
            channel, stream_of(channel, "Big Stream"), authoritative=authoritative
        )

    async def go_offline(self, channel: PlatformRef = CHANNEL) -> None:
        await self.tracker.observe_offline(channel)

    async def finish(self, download_id: str, status: DownloadStatus, error: str | None = None):
        """What the download engine does when a recording ends."""
        from dataclasses import replace

        from twick_hub.domain.events import DownloadFinished

        download = await self.downloads.get(download_id)
        assert download is not None
        await self.downloads.save(replace(download, status=status, error_message=error))
        await self.bus.publish(DownloadFinished(download_id, status, error))
