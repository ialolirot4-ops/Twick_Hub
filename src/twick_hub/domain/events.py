"""Internal domain events — Master Plan §41 (FASE 4d): "Conectar OFFLINE
→ ONLINE mediante eventos internos." "Internal" means exactly that: a
plain, in-process publish/subscribe mechanism, unrelated to Twitch's own
(now-shut-down) PubSub product. This is what lets
``TwitchEventSubProvider`` (Infrastructure) announce a live-status change
without knowing — or needing to know — who ends up reacting to it
(Favorites, Notifications, ScheduledDownload's ON_NEXT_LIVE trigger, the
UI). None of those consumers exist yet (FASE 9-11); this phase only
builds the bus and publishes onto it.

No PySide6 here either — same reasoning as the rest of ``domain/``.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from twick_hub.domain.content import Stream
from twick_hub.domain.enums import DownloadStatus
from twick_hub.domain.value_objects import PlatformRef

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ChannelWentOnline:
    """``initial`` is True when the live monitor's *first* observation of
    this channel found it already live — the real go-live moment is
    unknown (see ``Stream.started_at``). A consumer that only wants true
    transitions (e.g. a "went live" notification) skips ``initial``
    events; one that wants to catch up on a stream already in progress
    (e.g. auto-download) does not.
    """

    channel_ref: PlatformRef
    stream: Stream
    initial: bool = False


@dataclass(frozen=True, slots=True)
class ChannelWentOffline:
    channel_ref: PlatformRef


@dataclass(frozen=True, slots=True)
class DownloadFinished:
    """A download reached a terminal state (COMPLETED, FAILED or
    CANCELLED). Published by the download engine so whoever started it
    — the scheduler, auto-download, a future NotificationService — learns
    the outcome without polling the repository (FASE 11)."""

    download_id: str
    status: DownloadStatus
    error_message: str | None = None


DomainEvent = ChannelWentOnline | ChannelWentOffline | DownloadFinished
EventHandler = Callable[[DomainEvent], "Awaitable[None] | None"]


class EventBus:
    """Deliberately minimal: subscribe a handler, publish an event, every
    subscriber gets called. No topics/filtering — with two event types
    total so far, a handler just checks ``isinstance`` if it only cares
    about one of them.
    """

    def __init__(self) -> None:
        self._handlers: list[EventHandler] = []

    def subscribe(self, handler: EventHandler) -> None:
        self._handlers.append(handler)

    def unsubscribe(self, handler: EventHandler) -> None:
        if handler in self._handlers:
            self._handlers.remove(handler)

    async def publish(self, event: DomainEvent) -> None:
        """Delivers ``event`` to every subscriber. A subscriber that
        raises is logged and skipped — one faulty consumer must neither
        stop the others from hearing the event nor propagate into the
        live monitor that published it (FASE 10 retroactive fix, see
        docs/architecture-decisions.md).
        """
        for handler in list(self._handlers):
            try:
                result = handler(event)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                logger.exception("event handler %r failed for %s", handler, type(event).__name__)
