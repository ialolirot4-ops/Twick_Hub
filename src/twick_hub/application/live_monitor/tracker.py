"""Single source of truth for "is this channel live right now", and the
only place that turns observations into ``ChannelWentOnline`` /
``ChannelWentOffline`` events.

Several backends can watch the same channel at different moments — the
EventSub push feed, the slow reconcile poll that backs it up, a fast
poll for channels beyond EventSub's capacity, or a channel migrating
between them. Each just reports what it saw; the tracker compares it with
what it already knew and publishes **only a real transition**, so every
downstream consumer (notifications, auto-download, UI) gets each go-live
exactly once no matter how many backends noticed it.

Backends never publish onto the public bus themselves. The EventSub
provider (FASE 4d) publishes onto a *private* bus that the tracker
listens to (``attach``); the tracker republishes onto the public one.
"""

from __future__ import annotations

from typing import Protocol

from twick_hub.domain.content import Stream
from twick_hub.domain.events import ChannelWentOffline, ChannelWentOnline, DomainEvent, EventBus
from twick_hub.domain.value_objects import PlatformRef


class LiveObserver(Protocol):
    """What a monitor backend needs from the tracker. Both methods return
    whether the observation was news (a first sighting or a transition),
    which the polling policy uses to decide how fast to keep polling."""

    async def observe_live(
        self, channel_ref: PlatformRef, stream: Stream, *, authoritative: bool = False
    ) -> bool: ...

    async def observe_offline(self, channel_ref: PlatformRef) -> bool: ...


class LiveStateTracker:
    def __init__(self, public_bus: EventBus) -> None:
        self._bus = public_bus
        self._live: dict[PlatformRef, Stream] = {}
        self._known: set[PlatformRef] = set()

    def attach(self, private_bus: EventBus) -> None:
        """Listens to a backend's private bus (Twitch EventSub publishes
        onto one). Events arriving this way are push notifications — a
        definitive transition, hence ``authoritative``."""
        private_bus.subscribe(self._handle_backend_event)

    async def _handle_backend_event(self, event: DomainEvent) -> None:
        if isinstance(event, ChannelWentOnline):
            await self.observe_live(event.channel_ref, event.stream, authoritative=True)
        elif isinstance(event, ChannelWentOffline):
            await self.observe_offline(event.channel_ref)

    async def observe_live(
        self, channel_ref: PlatformRef, stream: Stream, *, authoritative: bool = False
    ) -> bool:
        """``authoritative`` marks a source that *announces transitions*
        (a push event): its "online" is a real go-live even for a channel
        never seen before. A poll result for a never-seen channel is
        instead an ``initial`` sighting — it was live before we looked."""
        was_known = channel_ref in self._known
        was_live = channel_ref in self._live
        self._known.add(channel_ref)
        self._live[channel_ref] = stream  # keep title/viewers fresh even without an event
        if was_live:
            return False
        await self._bus.publish(
            ChannelWentOnline(channel_ref, stream, initial=not was_known and not authoritative)
        )
        return True

    async def observe_offline(self, channel_ref: PlatformRef) -> bool:
        was_known = channel_ref in self._known
        was_live = channel_ref in self._live
        self._known.add(channel_ref)
        self._live.pop(channel_ref, None)
        if was_live:
            await self._bus.publish(ChannelWentOffline(channel_ref))
            return True
        return not was_known  # first sighting (offline) is news for pacing, but no event

    def forget(self, channel_ref: PlatformRef) -> None:
        """Drops everything known about a channel that is no longer
        watched (its favorite was removed). No event: nobody asked to be
        told it "went offline" just because we stopped looking."""
        self._known.discard(channel_ref)
        self._live.pop(channel_ref, None)

    def is_live(self, channel_ref: PlatformRef) -> bool | None:
        """``None`` means never observed — distinct from known-offline."""
        if channel_ref in self._live:
            return True
        return False if channel_ref in self._known else None

    def stream_of(self, channel_ref: PlatformRef) -> Stream | None:
        return self._live.get(channel_ref)

    @property
    def live_channels(self) -> frozenset[PlatformRef]:
        return frozenset(self._live)
