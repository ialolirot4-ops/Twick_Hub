"""Consumption metrics for the live monitor (Master Plan §47: "Medir: CPU,
RAM, requests, reconnects").

Requests and reconnects are counted exactly, by the backends that make
them (``MonitorStats``). CPU and RAM are **process-wide**: an in-process
monitor's own share can't be separated from the rest of the app by the
operating system, so ``cpu_percent`` and ``rss_bytes`` describe Twick Hub
as a whole. Read them as "did enabling the monitor move the needle", by
comparing a snapshot with and without it — not as the monitor's own bill.

A metric that can't be measured is ``None``, never an invented number.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from twick_hub.domain.enums import Platform
from twick_hub.domain.monitoring import MonitorStats, MonitorStatsSource


@dataclass(frozen=True, slots=True)
class ResourceSample:
    cpu_seconds: float  # user + system CPU time consumed by this process so far
    rss_bytes: int | None


@runtime_checkable
class ResourceProbe(Protocol):
    """Reads this process's resource use. The real implementation
    (``infrastructure/monitoring``) needs an OS-specific library, which
    Application must not import; tests supply a scripted fake."""

    def sample(self) -> ResourceSample: ...


@dataclass(frozen=True, slots=True)
class LiveMonitorSnapshot:
    taken_at: float  # monotonic seconds
    per_platform: Mapping[Platform, MonitorStats]
    total: MonitorStats
    live_channels: int
    cpu_percent: float | None  # process-wide, since the previous snapshot; None on the first
    rss_bytes: int | None
    requests_per_minute: float | None  # since the previous snapshot; None on the first

    def as_dict(self) -> dict[str, object]:
        """Plain, JSON-serialisable form for logging or a future
        diagnostics page."""
        return {
            "cpu_percent": self.cpu_percent,
            "rss_bytes": self.rss_bytes,
            "requests_per_minute": self.requests_per_minute,
            "live_channels": self.live_channels,
            "total": _stats_dict(self.total),
            "per_platform": {p.value: _stats_dict(s) for p, s in self.per_platform.items()},
        }


def _stats_dict(stats: MonitorStats) -> dict[str, float | int]:
    return {
        "requests": stats.requests,
        "polls": stats.polls,
        "errors": stats.errors,
        "rate_limited": stats.rate_limited,
        "reconnects": stats.reconnects,
        "abnormal_disconnects": stats.abnormal_disconnects,
        "channels_watched": stats.channels_watched,
        "poll_interval_seconds": stats.poll_interval_seconds,
    }


class LiveMonitorMetrics:
    def __init__(
        self,
        sources: Callable[[], Mapping[Platform, MonitorStatsSource]],
        live_channel_count: Callable[[], int],
        probe: ResourceProbe,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._sources = sources
        self._live_channel_count = live_channel_count
        self._probe = probe
        self._clock = clock
        self._previous: tuple[float, ResourceSample, int] | None = None

    def snapshot(self) -> LiveMonitorSnapshot:
        now = self._clock()
        sample = self._probe.sample()
        per_platform = {platform: source.stats() for platform, source in self._sources().items()}
        total = MonitorStats()
        for stats in per_platform.values():
            total = total + stats

        cpu_percent: float | None = None
        requests_per_minute: float | None = None
        if self._previous is not None:
            prev_time, prev_sample, prev_requests = self._previous
            elapsed = now - prev_time
            if elapsed > 0:
                cpu_percent = (sample.cpu_seconds - prev_sample.cpu_seconds) / elapsed * 100
                requests_per_minute = (total.requests - prev_requests) / elapsed * 60
        self._previous = (now, sample, total.requests)

        return LiveMonitorSnapshot(
            taken_at=now,
            per_platform=per_platform,
            total=total,
            live_channels=self._live_channel_count(),
            cpu_percent=cpu_percent,
            rss_bytes=sample.rss_bytes,
            requests_per_minute=requests_per_minute,
        )
