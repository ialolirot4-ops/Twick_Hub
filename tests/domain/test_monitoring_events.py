from __future__ import annotations

import logging

from tests.application.live_monitor.fakes import ref, stream_of
from twick_hub.domain.errors import LiveMonitorCapacityError, RateLimitedError
from twick_hub.domain.events import ChannelWentOffline, ChannelWentOnline, EventBus

A = ref("a")


def test_channel_went_online_initial_defaults_to_false():
    assert ChannelWentOnline(A, stream_of(A)).initial is False


async def test_a_failing_subscriber_does_not_stop_the_others_or_the_publisher(caplog):
    bus = EventBus()
    heard = []

    def broken(event):
        raise RuntimeError("bad consumer")

    async def broken_async(event):
        raise RuntimeError("bad async consumer")

    bus.subscribe(broken)
    bus.subscribe(broken_async)
    bus.subscribe(heard.append)

    with caplog.at_level(logging.ERROR):
        await bus.publish(ChannelWentOffline(A))  # must not raise

    assert heard == [ChannelWentOffline(A)]
    assert sum("event handler" in r.message for r in caplog.records) == 2


def test_rate_limited_error_carries_retry_after():
    error = RateLimitedError("slow", retry_after=3.5)
    assert error.retry_after == 3.5
    assert RateLimitedError().retry_after is None


def test_capacity_error_is_its_own_type():
    assert not issubclass(LiveMonitorCapacityError, RateLimitedError)


# FASE 18 — Testing: ``unsubscribe`` had no coverage at all.


async def test_unsubscribe_stops_a_handler_from_receiving_future_events():
    bus = EventBus()
    heard = []
    bus.subscribe(heard.append)
    bus.unsubscribe(heard.append)

    await bus.publish(ChannelWentOffline(A))

    assert heard == []


def test_unsubscribe_is_a_no_op_for_a_handler_never_subscribed():
    bus = EventBus()

    bus.unsubscribe(lambda event: None)  # must not raise
