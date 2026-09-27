from __future__ import annotations

from tests.application.live_monitor.fakes import collecting_bus, ref, stream_of
from twick_hub.application.live_monitor.tracker import LiveStateTracker
from twick_hub.domain.events import ChannelWentOffline, ChannelWentOnline, EventBus

A = ref("a")


async def test_first_sighting_live_is_an_initial_online_event():
    bus, seen = collecting_bus()
    tracker = LiveStateTracker(bus)

    news = await tracker.observe_live(A, stream_of(A))

    assert news is True
    assert seen == [ChannelWentOnline(A, stream_of(A), initial=True)]
    assert tracker.is_live(A) is True


async def test_repeated_live_observations_publish_once_but_refresh_the_stream():
    bus, seen = collecting_bus()
    tracker = LiveStateTracker(bus)
    await tracker.observe_live(A, stream_of(A, "old"))

    news = await tracker.observe_live(A, stream_of(A, "new title"))

    assert news is False
    assert len(seen) == 1
    stream = tracker.stream_of(A)
    assert stream is not None
    assert stream.title == "new title"


async def test_offline_to_live_transition_is_not_initial():
    bus, seen = collecting_bus()
    tracker = LiveStateTracker(bus)
    await tracker.observe_offline(A)

    await tracker.observe_live(A, stream_of(A))

    assert seen == [ChannelWentOnline(A, stream_of(A), initial=False)]


async def test_live_to_offline_publishes_once():
    bus, seen = collecting_bus()
    tracker = LiveStateTracker(bus)
    await tracker.observe_live(A, stream_of(A))

    assert await tracker.observe_offline(A) is True
    assert await tracker.observe_offline(A) is False

    assert [type(e) for e in seen] == [ChannelWentOnline, ChannelWentOffline]
    assert tracker.is_live(A) is False


async def test_first_sighting_offline_publishes_nothing_but_counts_as_news_for_pacing():
    bus, seen = collecting_bus()
    tracker = LiveStateTracker(bus)

    assert await tracker.observe_offline(A) is True  # first sighting
    assert await tracker.observe_offline(A) is False

    assert seen == []


async def test_authoritative_online_for_an_unseen_channel_is_a_real_transition():
    bus, seen = collecting_bus()
    tracker = LiveStateTracker(bus)

    await tracker.observe_live(A, stream_of(A), authoritative=True)

    assert seen == [ChannelWentOnline(A, stream_of(A), initial=False)]


async def test_two_backends_reporting_the_same_go_live_publish_it_once():
    bus, seen = collecting_bus()
    tracker = LiveStateTracker(bus)

    await tracker.observe_live(A, stream_of(A), authoritative=True)  # EventSub
    await tracker.observe_live(A, stream_of(A))  # the reconcile poll, later

    assert len(seen) == 1


async def test_is_live_is_none_for_a_never_observed_channel():
    assert LiveStateTracker(EventBus()).is_live(A) is None


async def test_forget_drops_state_and_publishes_nothing():
    bus, seen = collecting_bus()
    tracker = LiveStateTracker(bus)
    await tracker.observe_live(A, stream_of(A))

    tracker.forget(A)

    assert tracker.is_live(A) is None
    assert tracker.live_channels == frozenset()
    assert len(seen) == 1  # only the original online event

    await tracker.observe_live(A, stream_of(A))  # re-added later: a fresh initial sighting
    assert seen[-1] == ChannelWentOnline(A, stream_of(A), initial=True)


async def test_attach_bridges_a_private_backend_bus_to_the_public_one():
    public_bus, seen = collecting_bus()
    private_bus = EventBus()
    tracker = LiveStateTracker(public_bus)
    tracker.attach(private_bus)

    await private_bus.publish(ChannelWentOnline(A, stream_of(A)))
    await private_bus.publish(ChannelWentOnline(A, stream_of(A)))  # duplicate push
    await private_bus.publish(ChannelWentOffline(A))

    assert seen == [ChannelWentOnline(A, stream_of(A), initial=False), ChannelWentOffline(A)]
