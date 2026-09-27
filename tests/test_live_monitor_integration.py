"""FASE 10 end to end with the *real* adapters (only the network is
faked, at the transport / socket boundary): Twitch EventSub provider +
Helix batch provider + Kick batch provider, wired through the hybrid /
polling monitors, the tracker and the service to the public event bus.
"""

from __future__ import annotations

import asyncio

import httpx

from tests.application.fakes import InMemoryFavoriteRepository
from tests.application.live_monitor.fakes import collecting_bus
from tests.infrastructure.twitch.eventsub.test_provider import (
    FakeConnection,
    FakeConnector,
    FakeLiveStreamProvider,
    _notification,
    _welcome,
)
from twick_hub.application.live_monitor.hybrid_monitor import HybridLiveMonitor
from twick_hub.application.live_monitor.polling_monitor import PollingLiveMonitor
from twick_hub.application.live_monitor.polling_policy import PollingConfig
from twick_hub.application.live_monitor.service import LiveMonitorService
from twick_hub.application.live_monitor.tracker import LiveStateTracker
from twick_hub.application.platform_registry import PlatformAdapters, PlatformRegistry
from twick_hub.domain.collections import Favorite
from twick_hub.domain.enums import Platform
from twick_hub.domain.events import ChannelWentOffline, ChannelWentOnline, EventBus
from twick_hub.domain.value_objects import PlatformRef
from twick_hub.infrastructure.kick.client import KickAPIClient
from twick_hub.infrastructure.kick.livestream_batch import KickBatchLiveStatusProvider
from twick_hub.infrastructure.monitoring.process_probe import PsutilResourceProbe
from twick_hub.infrastructure.twitch.eventsub.provider import TwitchEventSubProvider
from twick_hub.infrastructure.twitch.helix_streams import TwitchBatchLiveStatusProvider

_MANUAL = PollingConfig(base_interval=60, jitter_ratio=0.0)
_RECONCILE = PollingConfig(
    base_interval=900, max_quiet_interval=900, max_backoff_interval=1800, jitter_ratio=0.0
)


def _twitch(i: int) -> PlatformRef:
    return PlatformRef(platform=Platform.TWITCH, external_id=str(i))


def _kick(i: int) -> PlatformRef:
    return PlatformRef(platform=Platform.KICK, external_id=str(i))


async def test_twitch_seven_favorites_five_push_two_polled_and_kick_polled_all_reach_one_bus():
    # --- Twitch: EventSub (5 slots) + Helix batch --------------------------
    helix_live: set[str] = {"6"}  # overflow channel 6 is already live at startup
    helix_requests: list[httpx.Request] = []

    def helix_handler(request: httpx.Request) -> httpx.Response:
        helix_requests.append(request)
        asked = request.url.params.get_list("user_id")
        data = [
            {
                "id": f"s{uid}",
                "user_id": uid,
                "type": "live",
                "title": "t",
                "started_at": "2026-09-01T10:00:00Z",
                "viewer_count": 3,
            }
            for uid in asked
            if uid in helix_live
        ]
        return httpx.Response(200, json={"data": data})

    eventsub_calls = [0]

    def eventsub_handler(request: httpx.Request) -> httpx.Response:
        eventsub_calls[0] += 1
        return httpx.Response(200, json={"data": [{"id": f"sub{eventsub_calls[0]}"}]})

    connection = FakeConnection([_welcome(), _notification("n1", "stream.online", "1")])
    private_bus = EventBus()
    public_bus, events = collecting_bus()
    tracker = LiveStateTracker(public_bus)
    tracker.attach(private_bus)

    helix = TwitchBatchLiveStatusProvider(
        httpx.AsyncClient(transport=httpx.MockTransport(helix_handler)), lambda: "user-token"
    )
    eventsub = TwitchEventSubProvider(
        httpx.AsyncClient(transport=httpx.MockTransport(eventsub_handler)),
        FakeLiveStreamProvider(),
        lambda: "user-token",
        private_bus,
        connector=FakeConnector([connection]),
    )
    twitch_monitor = HybridLiveMonitor(
        eventsub,
        PollingLiveMonitor(helix, tracker, config=_MANUAL, label="twitch fast"),
        PollingLiveMonitor(helix, tracker, config=_RECONCILE, label="twitch reconcile"),
    )

    # --- Kick: batch polling only ------------------------------------------
    kick_live = {"2"}

    def kick_handler(request: httpx.Request) -> httpx.Response:
        asked = request.url.params.get_list("broadcaster_user_id")
        data = [
            {
                "broadcaster_user_id": int(i),
                "slug": f"k{i}",
                "stream_title": "kt",
                "viewer_count": 1,
                "started_at": "2026-09-01T09:00:00Z",
            }
            for i in asked
            if i in kick_live
        ]
        return httpx.Response(200, json={"data": data})

    kick_client = KickAPIClient(
        httpx.AsyncClient(transport=httpx.MockTransport(kick_handler)), lambda: "kick-token"
    )
    kick_monitor = PollingLiveMonitor(
        KickBatchLiveStatusProvider(kick_client), tracker, config=_MANUAL, label="kick"
    )

    # --- favorites: 7 on Twitch, 3 on Kick ---------------------------------
    favorites = InMemoryFavoriteRepository()
    for position, ref in enumerate(
        [_twitch(i) for i in range(1, 8)] + [_kick(i) for i in (1, 2, 3)]
    ):
        await favorites.save(Favorite(channel_ref=ref, position=position))
    registry = PlatformRegistry(
        {
            Platform.TWITCH: PlatformAdapters(live_monitor=twitch_monitor),
            Platform.KICK: PlatformAdapters(live_monitor=kick_monitor),
        }
    )
    service = LiveMonitorService(favorites, registry, tracker, PsutilResourceProbe())

    report = await service.sync()

    assert report.failed == () and report.unsupported == ()
    assert len(report.subscribed) == 10
    # EventSub's budget is spent on the first five; the rest fall back to polling.
    assert twitch_monitor.push_channels == {_twitch(i) for i in range(1, 6)}
    assert twitch_monitor.polled_channels == {_twitch(6), _twitch(7)}
    assert eventsub_calls[0] == 10  # 5 channels × (online + offline)

    # Startup polls: fast poller (6, 7), reconcile poller (1..5) and Kick (1..3).
    await twitch_monitor._fallback.poll_once()
    await twitch_monitor._reconciler.poll_once()
    await kick_monitor.poll_once()
    initial = [e for e in events if isinstance(e, ChannelWentOnline)]
    assert {(e.channel_ref, e.initial) for e in initial} == {(_twitch(6), True), (_kick(2), True)}

    # A real push notification: channel 1 goes live → one non-initial event.
    events.clear()
    await eventsub._receive_and_handle_one()
    (only_event,) = events
    assert isinstance(only_event, ChannelWentOnline)
    assert (only_event.channel_ref, only_event.initial) == (_twitch(1), False)

    # The slow reconcile poll now also sees channel 1 live: no duplicate event.
    helix_live.add("1")
    events.clear()
    await twitch_monitor._reconciler.poll_once()
    assert events == []

    # Kick's channel 2 ends its stream → exactly one offline event.
    kick_live.clear()
    await kick_monitor.poll_once()
    assert events == [ChannelWentOffline(_kick(2))]

    # Consumption: batching means 3 Twitch polls + 2 Kick polls = 5 poll
    # requests for 10 channels (a per-channel poll would have been 10 per round).
    snapshot = service.metrics()
    assert snapshot.per_platform[Platform.KICK].requests == 2
    assert snapshot.per_platform[Platform.TWITCH].polls == 3
    assert len(helix_requests) == 3
    assert snapshot.total.channels_watched == 10
    assert snapshot.rss_bytes is not None and snapshot.rss_bytes > 0
    assert snapshot.live_channels == 2  # twitch 6 and twitch 1 (kick 2 went offline)


async def test_removing_a_push_favorite_promotes_a_polled_one_end_to_end():
    def ok(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"id": "sub"}]})

    private_bus = EventBus()
    public_bus, _ = collecting_bus()
    tracker = LiveStateTracker(public_bus)
    helix = TwitchBatchLiveStatusProvider(
        httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"data": []}))
        ),
        lambda: "t",
    )
    eventsub = TwitchEventSubProvider(
        httpx.AsyncClient(transport=httpx.MockTransport(ok)),
        FakeLiveStreamProvider(),
        lambda: "t",
        private_bus,
        connector=FakeConnector([FakeConnection([_welcome()])]),
    )
    monitor = HybridLiveMonitor(
        eventsub,
        PollingLiveMonitor(helix, tracker, config=_MANUAL),
        PollingLiveMonitor(helix, tracker, config=_RECONCILE),
    )
    favorites = InMemoryFavoriteRepository()
    saved = []
    for position in range(6):
        favorite = Favorite(channel_ref=_twitch(position + 1), position=position)
        saved.append(favorite)
        await favorites.save(favorite)
    registry = PlatformRegistry({Platform.TWITCH: PlatformAdapters(live_monitor=monitor)})
    service = LiveMonitorService(favorites, registry, tracker, PsutilResourceProbe())
    await service.sync()
    assert monitor.polled_channels == {_twitch(6)}

    await favorites.delete(saved[0].id)  # the user removes their first favorite
    await service.sync()

    assert monitor.polled_channels == frozenset()  # channel 6 got the freed push slot
    assert _twitch(6) in monitor.push_channels
    assert eventsub.capacity.used_cost == 10
    await asyncio.sleep(0)
