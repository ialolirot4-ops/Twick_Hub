"""Starts a recording of a channel that is live right now — the one path
both auto-download and scheduled downloads go through, so they can never
disagree about quality selection, file naming, or whether a channel is
already being recorded.

What it deliberately does *not* do is wait: it checks "is the channel live?"
once and either records or raises ``ChannelNotLiveError``. Waiting for a
go-live is the caller's business (an event listener, the scheduler's
window) and costs nothing while it waits.

"Is it live" is answered from the FASE 10 live monitor's own
``LiveStateTracker`` — a cheap dict lookup, never a fresh network call —
rather than ``PlatformRegistry.get_live_stream()``. That single-channel
query only exists for platforms with their own ``LiveStreamProvider``
(Twitch); Kick has none (AD-48), so a recorder built on it could never
record a Kick channel. The tracker is populated by whichever backend is
watching the channel, on every platform alike, and by the time a consumer
receives ``ChannelWentOnline`` the tracker already reflects it — so this
is also race-free where a fresh query would not be.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime

from twick_hub.application.live_monitor.tracker import LiveStateTracker
from twick_hub.application.platform_registry import PlatformRegistry
from twick_hub.application.scheduling.destination import DestinationPlanner
from twick_hub.application.scheduling.quality import NoQualitiesError, select_quality
from twick_hub.domain.downloads import Download, DownloadJob
from twick_hub.domain.enums import DownloadStatus, MediaKind
from twick_hub.domain.events import DomainEvent, DownloadFinished, EventBus
from twick_hub.domain.protocols import DownloadEngine, DownloadRepository
from twick_hub.domain.value_objects import Media, PlatformRef

logger = logging.getLogger(__name__)

_IN_FLIGHT = (
    DownloadStatus.QUEUED,
    DownloadStatus.PREPARING,
    DownloadStatus.DOWNLOADING,
    DownloadStatus.PROCESSING,
    DownloadStatus.PAUSED,
)


class ChannelNotLiveError(Exception):
    """Not an error in the usual sense: the channel simply isn't live."""


class AlreadyRecordingError(Exception):
    """This channel already has a recording in flight; ``download_id`` is it."""

    def __init__(self, download_id: str) -> None:
        super().__init__(f"already recording (download {download_id})")
        self.download_id = download_id


class RecordingUnavailableError(Exception):
    """Recording this channel cannot work no matter how often it is
    retried (the platform has no playback support, or offers no quality)."""


@dataclass(frozen=True, slots=True)
class RecordingRequest:
    channel_ref: PlatformRef
    quality: str = "best"
    file_format: str | None = None
    directory: str | None = None
    priority: int = 0


class RecordingService:
    def __init__(
        self,
        registry: PlatformRegistry,
        live_state: LiveStateTracker,
        downloads: DownloadRepository,
        engine: DownloadEngine,
        planner: DestinationPlanner,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._registry = registry
        self._live_state = live_state
        self._downloads = downloads
        self._engine = engine
        self._planner = planner
        self._clock = clock
        self._active: dict[PlatformRef, str] = {}
        self._locks: dict[PlatformRef, asyncio.Lock] = {}

    def attach(self, bus: EventBus) -> None:
        """Frees a channel for recording again once its download ends.
        Subscribe this *before* any consumer that retries on failure."""
        bus.subscribe(self._on_event)

    def _on_event(self, event: DomainEvent) -> None:
        if isinstance(event, DownloadFinished):
            for channel_ref, download_id in list(self._active.items()):
                if download_id == event.download_id:
                    del self._active[channel_ref]

    def active_download_of(self, channel_ref: PlatformRef) -> str | None:
        return self._active.get(channel_ref)

    async def start(self, request: RecordingRequest) -> Download:
        channel_ref = request.channel_ref
        # One lock per channel: an auto-download rule and a scheduled download
        # reacting to the same go-live at the same instant must produce one
        # recording, not two.
        async with self._locks.setdefault(channel_ref, asyncio.Lock()):
            existing = self._active.get(channel_ref)
            if existing is not None:
                raise AlreadyRecordingError(existing)

            stream = self._live_state.stream_of(channel_ref)
            if stream is None:
                raise ChannelNotLiveError(str(channel_ref))

            media = Media(
                kind=MediaKind.STREAM,
                ref=stream.ref,
                title=stream.title,
                channel_ref=channel_ref,
                thumbnail_url=stream.thumbnail_url,
            )
            qualities = await self._registry.available_qualities(media)
            try:
                choice = select_quality(request.quality, qualities)
            except NoQualitiesError as exc:
                raise RecordingUnavailableError(str(exc)) from exc
            if choice.fell_back:
                logger.info(
                    "%s: quality %r unavailable, recording %s",
                    channel_ref,
                    request.quality,
                    choice.label,
                )

            now = self._clock()
            destination = self._planner.plan(
                {
                    "channel": await self._channel_name(channel_ref),
                    "title": stream.title or "stream",
                    "category": stream.category or "unknown",
                    "quality": choice.label,
                    "date": now.strftime("%Y-%m-%d"),
                    "time": now.strftime("%H-%M-%S"),
                },
                directory=request.directory,
                extension=request.file_format,
                reserved=[
                    d.destination_path for d in await self._downloads.list_by_status(_IN_FLIGHT)
                ],
            )

            download = Download(
                media=media, destination_path=destination, quality_label=choice.label
            )
            await self._downloads.save(download)
            try:
                await self._engine.enqueue(
                    DownloadJob(download_id=download.id, priority=request.priority)
                )
            except Exception as exc:
                await self._downloads.save(
                    replace(download, status=DownloadStatus.FAILED, error_message=str(exc))
                )
                raise
            self._active[channel_ref] = download.id
            return download

    async def _channel_name(self, channel_ref: PlatformRef) -> str:
        try:
            return (await self._registry.get_channel(channel_ref)).user.username
        except Exception:  # noqa: BLE001 - a missing display name must not block a recording
            return channel_ref.external_id
