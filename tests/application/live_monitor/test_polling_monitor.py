from __future__ import annotations

import asyncio

import pytest

from tests.application.live_monitor.fakes import (
    FakeBatchProvider,
    RecordingObserver,
    collecting_bus,
    ref,
)
from twick_hub.application.live_monitor.polling_monitor import PollingLiveMonitor
from twick_hub.application.live_monitor.polling_policy import PollingConfig
from twick_hub.application.live_monitor.tracker import LiveStateTracker
from twick_hub.domain.errors import RateLimitedError
from twick_hub.domain.events import ChannelWentOffline, ChannelWentOnline
from twick_hub.domain.protocols import LiveMonitor

A, B, C = ref("a"), ref("b"), ref("c")
_CONFIG = PollingConfig(base_interval=60, jitter_ratio=0.0)


def _monitor(provider, observer=None, config=_CONFIG) -> PollingLiveMonitor:
    return PollingLiveMonitor(provider, observer or RecordingObserver(), config=config)


def test_satisfies_live_monitor_protocol():
    assert isinstance(_monitor(FakeBatchProvider()), LiveMonitor)


async def test_polls_every_watched_channel_in_one_batched_call():
    provider = FakeBatchProvider(live={B})
    observer = RecordingObserver()
    monitor = _monitor(provider, observer)
    for channel in (A, B, C):
        await monitor.subscribe(channel)

    await monitor.poll_once()

    assert provider.calls == [[A, B, C]]  # one call for all three, not three calls
    assert observer.events == [("offline", A), ("live", B), ("offline", C)]


async def test_poll_with_nothing_watched_makes_no_request():
    provider = FakeBatchProvider()

    await _monitor(provider).poll_once()

    assert provider.calls == []


async def test_subscribe_twice_watches_once_and_unsubscribe_stops_watching():
    provider = FakeBatchProvider()
    monitor = _monitor(provider)
    await monitor.subscribe(A)
    await monitor.subscribe(A)
    await monitor.unsubscribe(A)
    await monitor.unsubscribe(A)  # no-op

    await monitor.poll_once()

    assert monitor.watched == frozenset()
    assert provider.calls == []


async def test_unsubscribed_while_request_in_flight_is_not_reported():
    observer = RecordingObserver()
    gate = asyncio.Event()

    class SlowProvider(FakeBatchProvider):
        async def get_live_streams(self, channel_refs):
            await gate.wait()
            return await super().get_live_streams(channel_refs)

    monitor = _monitor(SlowProvider(live={A, B}), observer)
    await monitor.subscribe(A)
    await monitor.subscribe(B)

    task = asyncio.create_task(monitor.poll_once())
    await asyncio.sleep(0)
    await monitor.unsubscribe(A)
    gate.set()
    await task

    assert observer.events == [("live", B)]


async def test_stats_count_requests_polls_and_report_the_interval():
    provider = FakeBatchProvider(requests_per_call=3)
    monitor = _monitor(provider)
    await monitor.subscribe(A)

    await monitor.poll_once()
    await monitor.poll_once()

    stats = monitor.stats()
    assert (stats.requests, stats.polls, stats.errors) == (6, 2, 0)
    assert stats.channels_watched == 1
    assert stats.poll_interval_seconds == 60


async def test_idle_monitor_reports_zero_interval():
    assert _monitor(FakeBatchProvider()).stats().poll_interval_seconds == 0.0


async def test_a_failed_poll_is_counted_backs_off_and_does_not_raise():
    provider = FakeBatchProvider(script=[RuntimeError("boom")])
    observer = RecordingObserver()
    monitor = _monitor(provider, observer)
    await monitor.subscribe(A)

    await monitor.poll_once()  # must not raise

    stats = monitor.stats()
    assert (stats.errors, stats.polls, stats.requests) == (1, 0, 0)
    assert monitor.current_interval == 120  # backed off
    assert observer.events == []  # state untouched: a failure is not "offline"


async def test_rate_limit_is_counted_separately_and_honours_retry_after():
    provider = FakeBatchProvider(script=[RateLimitedError("slow", retry_after=400)])
    monitor = _monitor(provider)
    await monitor.subscribe(A)

    await monitor.poll_once()

    stats = monitor.stats()
    assert stats.rate_limited == 1
    assert stats.errors == 1
    assert monitor.current_interval == 400


async def test_recovers_to_base_interval_after_an_outage():
    provider = FakeBatchProvider(script=[RuntimeError("boom"), RuntimeError("boom"), set()])
    monitor = _monitor(provider)
    await monitor.subscribe(A)
    await monitor.poll_once()
    await monitor.poll_once()
    assert monitor.current_interval == 240

    await monitor.poll_once()

    assert monitor.current_interval == 60


async def test_quiet_polls_lengthen_the_interval_and_news_resets_it():
    config = PollingConfig(
        base_interval=60,
        quiet_polls_before_stretch=2,
        quiet_stretch_factor=2.0,
        max_quiet_interval=240,
        jitter_ratio=0.0,
    )
    provider = FakeBatchProvider()
    tracker_bus, _ = collecting_bus()
    monitor = PollingLiveMonitor(provider, LiveStateTracker(tracker_bus), config=config)
    await monitor.subscribe(A)

    await monitor.poll_once()  # first sighting is news
    assert monitor.current_interval == 60
    await monitor.poll_once()
    await monitor.poll_once()  # 2 quiet polls → stretch
    assert monitor.current_interval == 120

    provider.live = {A}  # goes live
    await monitor.poll_once()
    assert monitor.current_interval == 60


async def test_end_to_end_with_the_real_tracker_publishes_transitions_once():
    bus, seen = collecting_bus()
    provider = FakeBatchProvider(script=[{A}, {A}, set(), set()])
    monitor = PollingLiveMonitor(provider, LiveStateTracker(bus), config=_CONFIG)
    await monitor.subscribe(A)

    for _ in range(4):
        await monitor.poll_once()

    assert [type(e) for e in seen] == [ChannelWentOnline, ChannelWentOffline]
    online = seen[0]
    assert isinstance(online, ChannelWentOnline)
    assert online.initial is True  # it was already live when first looked at


# --- run_forever (real, tiny delays) -----------------------------------


_FAST = PollingConfig(
    base_interval=0.05, jitter_ratio=0.0, coalesce_seconds=0.0, max_quiet_interval=0.05
)


async def test_run_forever_sleeps_with_no_channels_and_wakes_promptly_on_subscribe():
    provider = FakeBatchProvider()
    # A long interval proves the first poll comes from the wake-up, not the timer.
    config = PollingConfig(
        base_interval=3600,
        jitter_ratio=0.0,
        coalesce_seconds=0.0,
        max_quiet_interval=3600,
        max_backoff_interval=3600,
    )
    monitor = _monitor(provider, config=config)
    task = asyncio.create_task(monitor.run_forever())

    await asyncio.sleep(0.05)
    assert provider.calls == []  # idle: no request, no timer

    await monitor.subscribe(A)
    await asyncio.sleep(0.05)
    assert provider.calls == [[A]]

    await monitor.stop()
    await asyncio.wait_for(task, timeout=1)


async def test_run_forever_polls_repeatedly_at_the_interval_and_stops_cleanly():
    provider = FakeBatchProvider()
    monitor = _monitor(provider, config=_FAST)
    await monitor.subscribe(A)
    task = asyncio.create_task(monitor.run_forever())

    await asyncio.sleep(0.3)
    await monitor.stop()
    await asyncio.wait_for(task, timeout=1)

    assert len(provider.calls) >= 3


async def test_a_burst_of_subscribes_costs_one_request():
    provider = FakeBatchProvider()
    config = PollingConfig(
        base_interval=3600,
        jitter_ratio=0.0,
        coalesce_seconds=0.05,
        max_quiet_interval=3600,
        max_backoff_interval=3600,
    )
    monitor = _monitor(provider, config=config)
    task = asyncio.create_task(monitor.run_forever())
    await asyncio.sleep(0.01)

    for channel in (A, B, C):
        await monitor.subscribe(channel)
        await asyncio.sleep(0)
    await asyncio.sleep(0.2)

    assert provider.calls == [[A, B, C]]
    await monitor.stop()
    await asyncio.wait_for(task, timeout=1)


async def test_run_forever_can_be_cancelled_mid_wait():
    monitor = _monitor(FakeBatchProvider())
    task = asyncio.create_task(monitor.run_forever())
    await asyncio.sleep(0.01)

    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
