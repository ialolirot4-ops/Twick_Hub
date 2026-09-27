from __future__ import annotations

import asyncio
import contextlib

from tests.application.live_monitor.fakes import (
    FakeBatchProvider,
    FakePushMonitor,
    RecordingObserver,
    ref,
)
from twick_hub.application.live_monitor.hybrid_monitor import HybridLiveMonitor
from twick_hub.application.live_monitor.polling_monitor import PollingLiveMonitor
from twick_hub.application.live_monitor.polling_policy import PollingConfig
from twick_hub.domain.protocols import LiveMonitor

_CONFIG = PollingConfig(base_interval=60, jitter_ratio=0.0)


def _hybrid(capacity: int, provider=None, push: FakePushMonitor | None = None):
    provider = provider or FakeBatchProvider()
    observer = RecordingObserver()
    push = push or FakePushMonitor(capacity=capacity)
    fallback = PollingLiveMonitor(provider, observer, config=_CONFIG, label="fallback")
    reconciler = PollingLiveMonitor(
        provider,
        observer,
        config=PollingConfig(
            base_interval=900, max_quiet_interval=900, max_backoff_interval=1800, jitter_ratio=0.0
        ),
        label="reconciler",
    )
    return HybridLiveMonitor(push, fallback, reconciler), push, fallback, reconciler


def test_satisfies_live_monitor_protocol():
    hybrid, *_ = _hybrid(5)
    assert isinstance(hybrid, LiveMonitor)


async def test_channels_within_capacity_go_push_and_are_also_reconciled_slowly():
    hybrid, push, fallback, reconciler = _hybrid(2)

    await hybrid.subscribe(ref("a"))
    await hybrid.subscribe(ref("b"))

    assert push.subscribed == [ref("a"), ref("b")]
    assert hybrid.push_channels == {ref("a"), ref("b")}
    assert hybrid.polled_channels == frozenset()
    assert reconciler.watched == {ref("a"), ref("b")}
    assert fallback.watched == frozenset()


async def test_overflow_beyond_capacity_falls_back_to_the_fast_poller():
    hybrid, push, fallback, reconciler = _hybrid(2)
    for name in "abcd":
        await hybrid.subscribe(ref(name))

    assert hybrid.push_channels == {ref("a"), ref("b")}  # first come, first served
    assert hybrid.polled_channels == {ref("c"), ref("d")}
    assert fallback.watched == {ref("c"), ref("d")}
    assert reconciler.watched == {ref("a"), ref("b")}


async def test_subscribing_the_same_channel_twice_is_a_noop():
    hybrid, push, *_ = _hybrid(1)
    await hybrid.subscribe(ref("a"))
    await hybrid.subscribe(ref("a"))

    assert push.subscribed == [ref("a")]


async def test_a_non_capacity_push_failure_also_falls_back_and_is_counted():
    hybrid, push, fallback, _ = _hybrid(
        5, push=FakePushMonitor(capacity=5, fail_with=RuntimeError("401"))
    )

    await hybrid.subscribe(ref("a"))

    assert fallback.watched == {ref("a")}
    assert hybrid.stats().errors == 1


async def test_unsubscribing_a_push_channel_promotes_the_oldest_polled_one():
    hybrid, push, fallback, reconciler = _hybrid(1)
    for name in "abc":
        await hybrid.subscribe(ref(name))  # a → push; b, c → polled

    await hybrid.unsubscribe(ref("a"))

    assert push.subscribed == [ref("b")]
    assert hybrid.push_channels == {ref("b")}
    assert hybrid.polled_channels == {ref("c")}
    assert fallback.watched == {ref("c")}
    assert reconciler.watched == {ref("b")}  # a's reconcile watch is gone, b's added


async def test_unsubscribing_a_polled_channel_does_not_touch_push():
    hybrid, push, fallback, _ = _hybrid(1)
    await hybrid.subscribe(ref("a"))
    await hybrid.subscribe(ref("b"))

    await hybrid.unsubscribe(ref("b"))

    assert push.subscribed == [ref("a")]
    assert fallback.watched == frozenset()


async def test_unsubscribing_an_unknown_channel_is_a_noop():
    hybrid, *_ = _hybrid(1)
    await hybrid.unsubscribe(ref("zzz"))


async def test_revoked_push_subscription_demotes_the_channel_to_polling():
    hybrid, push, fallback, reconciler = _hybrid(2)
    await hybrid.subscribe(ref("a"))

    push.lose(ref("a"))
    push.lose(ref("a"))  # Twitch revokes online and offline separately: idempotent
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert hybrid.push_channels == frozenset()
    assert hybrid.polled_channels == {ref("a")}
    assert fallback.watched == {ref("a")}
    assert reconciler.watched == frozenset()
    assert push.subscribed == []  # its budget was released


async def test_push_loss_for_a_channel_not_in_push_is_ignored():
    hybrid, push, fallback, _ = _hybrid(1)
    await hybrid.subscribe(ref("a"))
    await hybrid.subscribe(ref("b"))  # polled

    push.lose(ref("b"))
    await asyncio.sleep(0)

    assert hybrid.polled_channels == {ref("b")}


async def test_stats_sum_the_backends_and_count_distinct_channels():
    provider = FakeBatchProvider()
    hybrid, push, fallback, reconciler = _hybrid(1, provider=provider)
    await hybrid.subscribe(ref("a"))
    await hybrid.subscribe(ref("b"))
    await fallback.poll_once()
    await reconciler.poll_once()

    stats = hybrid.stats()

    assert stats.requests == 2 + 1 + 1  # push (2) + fast poll + reconcile poll
    assert stats.reconnects == 1  # from the push backend
    assert stats.polls == 2
    assert stats.channels_watched == 2  # a and b, not a counted three times


async def test_run_forever_runs_all_three_backends_and_stops_cleanly():
    provider = FakeBatchProvider()
    fast = PollingConfig(
        base_interval=0.05,
        max_quiet_interval=0.05,
        max_backoff_interval=0.05,
        jitter_ratio=0.0,
        coalesce_seconds=0.0,
    )
    observer = RecordingObserver()
    push = FakePushMonitor(capacity=1)
    ran = []

    async def push_run():
        ran.append("push")
        await asyncio.sleep(3600)

    async def push_stop():
        return None

    push.run_forever = push_run  # type: ignore[attr-defined]
    push.stop = push_stop  # type: ignore[attr-defined]
    fallback = PollingLiveMonitor(provider, observer, config=fast)
    reconciler = PollingLiveMonitor(provider, observer, config=fast)
    hybrid = HybridLiveMonitor(push, fallback, reconciler)
    await hybrid.subscribe(ref("a"))
    await hybrid.subscribe(ref("b"))
    task = asyncio.create_task(hybrid.run_forever())

    await asyncio.sleep(0.2)
    assert ran == ["push"]
    assert len(provider.calls) >= 2  # fast poller (b) and reconcile poller (a) both ran

    await hybrid.stop()
    task.cancel()  # the fake push loop sleeps forever; cancellation is the real stop path
    with contextlib.suppress(asyncio.CancelledError):
        await task
