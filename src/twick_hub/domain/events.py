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
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from twick_hub.domain.content import Stream
from twick_hub.domain.value_objects import PlatformRef


@dataclass(frozen=True, slots=True)
class ChannelWentOnline:
    channel_ref: PlatformRef
    stream: Stream


@dataclass(frozen=True, slots=True)
class ChannelWentOffline:
    channel_ref: PlatformRef


DomainEvent = ChannelWentOnline | ChannelWentOffline
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
        for handler in list(self._handlers):
            result = handler(event)
            if inspect.isawaitable(result):
                await result
