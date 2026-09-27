"""Live-monitoring value objects and protocols (Master Plan §47, FASE 10).

Pure data + interfaces — no I/O, no PySide6. ``MonitorStats`` is the
common vocabulary every monitor backend (Twitch EventSub, the polling
backends) reports its own consumption in, so the application layer can
sum and compare them without knowing which mechanism produced which
number — Master Plan §47: "Medir: CPU, RAM, requests, reconnects."
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from twick_hub.domain.content import Stream
from twick_hub.domain.value_objects import PlatformRef


@dataclass(frozen=True, slots=True)
class MonitorStats:
    """Monotonic counters (plus two gauges) for one monitor backend.

    ``requests`` counts HTTP requests the backend itself made to the
    platform (poll requests; for push backends, subscription
    create/delete calls). ``reconnects`` is every WebSocket
    re-connection, graceful or not; ``abnormal_disconnects`` is the
    subset that was an unplanned drop. ``channels_watched`` and
    ``poll_interval_seconds`` are gauges, not counters: ``0.0`` means
    "this backend doesn't poll".
    """

    requests: int = 0
    polls: int = 0
    errors: int = 0
    rate_limited: int = 0
    reconnects: int = 0
    abnormal_disconnects: int = 0
    channels_watched: int = 0
    poll_interval_seconds: float = 0.0

    def __add__(self, other: MonitorStats) -> MonitorStats:
        return MonitorStats(
            requests=self.requests + other.requests,
            polls=self.polls + other.polls,
            errors=self.errors + other.errors,
            rate_limited=self.rate_limited + other.rate_limited,
            reconnects=self.reconnects + other.reconnects,
            abnormal_disconnects=self.abnormal_disconnects + other.abnormal_disconnects,
            channels_watched=self.channels_watched + other.channels_watched,
            # Summing an interval is meaningless. The fastest cadence that is
            # actually polling bounds how late a go-live can be noticed, so
            # that is the honest summary (0.0 = not polling, ignored).
            poll_interval_seconds=min(
                (v for v in (self.poll_interval_seconds, other.poll_interval_seconds) if v > 0),
                default=0.0,
            ),
        )


@dataclass(frozen=True, slots=True)
class LiveStatusBatch:
    """Result of one batched live-status lookup.

    ``live`` holds only channels that are live *as of this response*,
    keyed by channel ref; a requested channel missing from it is offline.
    ``requests_made`` is how many HTTP requests it took (a provider
    chunks internally to its API's per-request id limit), so the
    monitor's request counter reflects real network cost.
    """

    live: Mapping[PlatformRef, Stream]
    requests_made: int


@runtime_checkable
class MonitorStatsSource(Protocol):
    def stats(self) -> MonitorStats: ...


@runtime_checkable
class MonitorRunner(Protocol):
    """A monitor with a long-running loop (EventSub's receive loop, a
    polling loop). ``run_forever`` returns only after ``stop()``, or
    raises on a failure the caller's supervisor decides how to handle.
    """

    async def run_forever(self) -> None: ...

    async def stop(self) -> None: ...


@runtime_checkable
class PushLossNotifier(Protocol):
    """A push-based monitor that can tell its owner it silently lost
    coverage of one channel (e.g. Twitch revoked an EventSub
    subscription), so the owner can fall back to another mechanism.
    """

    def on_push_lost(self, handler: Callable[[PlatformRef], None]) -> None: ...
