"""Shared fakes for the live-monitor tests."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from twick_hub.application.live_monitor.metrics import ResourceSample
from twick_hub.domain.content import Stream
from twick_hub.domain.enums import Platform
from twick_hub.domain.events import DomainEvent, EventBus
from twick_hub.domain.monitoring import LiveStatusBatch, MonitorStats
from twick_hub.domain.value_objects import PlatformRef


def ref(external_id: str, platform: Platform = Platform.KICK) -> PlatformRef:
    return PlatformRef(platform=platform, external_id=external_id)


def stream_of(channel_ref: PlatformRef, title: str = "live") -> Stream:
    return Stream(
        ref=PlatformRef(platform=channel_ref.platform, external_id=f"s-{channel_ref.external_id}"),
        channel_ref=channel_ref,
        title=title,
        category=None,
        started_at=datetime(2026, 9, 1, 10, 0, tzinfo=UTC),
        viewer_count=1,
    )


def collecting_bus() -> tuple[EventBus, list[DomainEvent]]:
    bus = EventBus()
    seen: list[DomainEvent] = []
    bus.subscribe(seen.append)
    return bus, seen


@dataclass
class FakeBatchProvider:
    """``live`` is what the next poll reports; ``script`` (if any) is
    consumed first — an Exception instance in it is raised instead."""

    live: set[PlatformRef] = field(default_factory=set)
    script: list[object] = field(default_factory=list)
    calls: list[list[PlatformRef]] = field(default_factory=list)
    requests_per_call: int = 1

    async def get_live_streams(self, channel_refs: Sequence[PlatformRef]) -> LiveStatusBatch:
        self.calls.append(list(channel_refs))
        if self.script:
            item = self.script.pop(0)
            if isinstance(item, Exception):
                raise item
            assert isinstance(item, set)
            self.live = item
        return LiveStatusBatch(
            live={r: stream_of(r) for r in channel_refs if r in self.live},
            requests_made=self.requests_per_call,
        )


@dataclass
class RecordingObserver:
    events: list[tuple[str, PlatformRef]] = field(default_factory=list)
    news: bool = True

    async def observe_live(self, channel_ref, stream, *, authoritative: bool = False) -> bool:
        self.events.append(("live", channel_ref))
        return self.news

    async def observe_offline(self, channel_ref) -> bool:
        self.events.append(("offline", channel_ref))
        return self.news


class FakeProbe:
    def __init__(self, samples: list[ResourceSample]) -> None:
        self._samples = list(samples)

    def sample(self) -> ResourceSample:
        return self._samples.pop(0) if len(self._samples) > 1 else self._samples[0]


@dataclass
class FakePushMonitor:
    """Stands in for TwitchEventSubProvider: fixed capacity, push-loss hook."""

    capacity: int
    subscribed: list[PlatformRef] = field(default_factory=list)
    fail_with: Exception | None = None
    _handlers: list = field(default_factory=list)
    stats_value: MonitorStats = field(
        default_factory=lambda: MonitorStats(requests=2, reconnects=1)
    )

    async def subscribe(self, channel_ref: PlatformRef) -> None:
        from twick_hub.domain.errors import LiveMonitorCapacityError

        if self.fail_with is not None:
            raise self.fail_with
        if channel_ref in self.subscribed:
            return
        if len(self.subscribed) >= self.capacity:
            raise LiveMonitorCapacityError("full")
        self.subscribed.append(channel_ref)

    async def unsubscribe(self, channel_ref: PlatformRef) -> None:
        if channel_ref in self.subscribed:
            self.subscribed.remove(channel_ref)

    def on_push_lost(self, handler) -> None:
        self._handlers.append(handler)

    def lose(self, channel_ref: PlatformRef) -> None:
        for handler in self._handlers:
            handler(channel_ref)

    def stats(self) -> MonitorStats:
        return self.stats_value
