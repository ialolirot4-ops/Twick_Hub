from __future__ import annotations

import pytest

from tests.application.live_monitor.fakes import FakeProbe
from twick_hub.application.live_monitor.metrics import LiveMonitorMetrics, ResourceSample
from twick_hub.domain.enums import Platform
from twick_hub.domain.monitoring import MonitorStats


class _Source:
    def __init__(self, stats: MonitorStats) -> None:
        self.value = stats

    def stats(self) -> MonitorStats:
        return self.value


def test_first_snapshot_has_no_rates_but_does_have_memory_and_totals():
    kick = _Source(MonitorStats(requests=4, polls=4, channels_watched=3))
    metrics = LiveMonitorMetrics(
        sources=lambda: {Platform.KICK: kick},
        live_channel_count=lambda: 2,
        probe=FakeProbe([ResourceSample(cpu_seconds=10.0, rss_bytes=90_000_000)]),
        clock=lambda: 100.0,
    )

    snap = metrics.snapshot()

    assert snap.cpu_percent is None
    assert snap.requests_per_minute is None
    assert snap.rss_bytes == 90_000_000
    assert snap.total.requests == 4
    assert snap.live_channels == 2


def test_cpu_percent_and_request_rate_are_computed_between_snapshots():
    twitch = _Source(MonitorStats(requests=10, reconnects=1))
    kick = _Source(MonitorStats(requests=0))
    times = iter([0.0, 60.0])
    metrics = LiveMonitorMetrics(
        sources=lambda: {Platform.TWITCH: twitch, Platform.KICK: kick},
        live_channel_count=lambda: 0,
        probe=FakeProbe([ResourceSample(1.0, 100), ResourceSample(1.6, 120)]),
        clock=lambda: next(times),
    )
    metrics.snapshot()
    twitch.value = MonitorStats(requests=14, reconnects=2)
    kick.value = MonitorStats(requests=6)

    snap = metrics.snapshot()

    assert snap.cpu_percent == pytest.approx(1.0)  # 0.6 CPU-seconds over 60 s
    assert snap.requests_per_minute == pytest.approx(10.0)  # (14+6) - 10 over one minute
    assert snap.total.requests == 20
    assert snap.total.reconnects == 2
    assert snap.per_platform[Platform.KICK].requests == 6


def test_an_unmeasurable_rss_stays_none():
    metrics = LiveMonitorMetrics(
        sources=dict,
        live_channel_count=lambda: 0,
        probe=FakeProbe([ResourceSample(0.0, None)]),
        clock=lambda: 0.0,
    )
    assert metrics.snapshot().rss_bytes is None


def test_zero_elapsed_time_does_not_divide_by_zero():
    metrics = LiveMonitorMetrics(
        sources=dict,
        live_channel_count=lambda: 0,
        probe=FakeProbe([ResourceSample(0.0, 1)]),
        clock=lambda: 5.0,
    )
    metrics.snapshot()
    assert metrics.snapshot().cpu_percent is None


def test_as_dict_is_plain_and_json_serialisable():
    import json

    metrics = LiveMonitorMetrics(
        sources=lambda: {Platform.KICK: _Source(MonitorStats(requests=1))},
        live_channel_count=lambda: 1,
        probe=FakeProbe([ResourceSample(0.0, 1)]),
        clock=lambda: 0.0,
    )

    data = metrics.snapshot().as_dict()

    assert json.loads(json.dumps(data))["per_platform"]["kick"]["requests"] == 1


def test_monitor_stats_add_sums_counters_and_reports_the_fastest_polling_cadence():
    a = MonitorStats(requests=1, errors=2, reconnects=1, poll_interval_seconds=60)
    b = MonitorStats(requests=3, rate_limited=1, channels_watched=2, poll_interval_seconds=900)

    total = a + b

    assert (total.requests, total.errors, total.rate_limited) == (4, 2, 1)
    assert total.reconnects == 1
    assert total.channels_watched == 2
    assert total.poll_interval_seconds == 60  # the fastest poller bounds detection latency
    assert (a + MonitorStats()).poll_interval_seconds == 60  # 0.0 = "not polling", ignored
    assert MonitorStats().__add__(MonitorStats()).poll_interval_seconds == 0.0
