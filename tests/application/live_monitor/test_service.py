from __future__ import annotations

import asyncio

from tests.application.fakes import InMemoryFavoriteRepository
from tests.application.live_monitor.fakes import (
    FakeBatchProvider,
    FakeProbe,
    collecting_bus,
    ref,
)
from twick_hub.application.live_monitor.metrics import ResourceSample
from twick_hub.application.live_monitor.polling_monitor import PollingLiveMonitor
from twick_hub.application.live_monitor.polling_policy import PollingConfig
from twick_hub.application.live_monitor.service import LiveMonitorService
from twick_hub.application.live_monitor.tracker import LiveStateTracker
from twick_hub.application.platform_registry import PlatformAdapters, PlatformRegistry
from twick_hub.domain.collections import Favorite
from twick_hub.domain.enums import Platform
from twick_hub.domain.events import ChannelWentOnline

_FAST = PollingConfig(
    base_interval=0.05,
    max_quiet_interval=0.05,
    max_backoff_interval=0.05,
    jitter_ratio=0.0,
    coalesce_seconds=0.0,
)


class _Fixture:
    def __init__(self, *, with_kick_monitor: bool = True) -> None:
        self.favorites = InMemoryFavoriteRepository()
        self.bus, self.events = collecting_bus()
        self.tracker = LiveStateTracker(self.bus)
        self.provider = FakeBatchProvider()
        self.kick = PollingLiveMonitor(self.provider, self.tracker, config=_FAST)
        adapters = {
            Platform.KICK: PlatformAdapters(live_monitor=self.kick if with_kick_monitor else None),
            Platform.TWITCH: PlatformAdapters(),
        }
        self.registry = PlatformRegistry(adapters)
        self.service = LiveMonitorService(
            self.favorites,
            self.registry,
            self.tracker,
            FakeProbe([ResourceSample(0.0, 1_000_000)]),
        )

    async def add(self, name: str, position: int = 0, **flags) -> Favorite:
        favorite = Favorite(channel_ref=ref(name), position=position, **flags)
        await self.favorites.save(favorite)
        return favorite


async def test_sync_subscribes_favorites_that_want_notifications_or_auto_download():
    f = _Fixture()
    await f.add("notify", position=0, notify_on_live=True)
    await f.add("auto", position=1, notify_on_live=False, auto_download=True)
    await f.add("silent", position=2, notify_on_live=False, auto_download=False)

    report = await f.service.sync()

    assert report.subscribed == (ref("notify"), ref("auto"))
    assert f.kick.watched == {ref("notify"), ref("auto")}  # "silent" costs nothing


async def test_sync_is_idempotent_and_reacts_to_changes():
    f = _Fixture()
    a = await f.add("a")
    await f.add("b", position=1)
    await f.service.sync()

    again = await f.service.sync()
    assert again.subscribed == () and again.unsubscribed == ()

    await f.favorites.delete(a.id)
    changed = await f.service.sync()

    assert changed.unsubscribed == (ref("a"),)
    assert f.kick.watched == {ref("b")}


async def test_turning_notifications_off_stops_watching_that_channel():
    f = _Fixture()
    favorite = await f.add("a")
    await f.service.sync()

    from dataclasses import replace

    await f.favorites.save(replace(favorite, notify_on_live=False))
    report = await f.service.sync()

    assert report.unsubscribed == (ref("a"),)
    assert f.kick.watched == frozenset()


async def test_unsubscribing_forgets_tracker_state_for_that_channel():
    f = _Fixture()
    favorite = await f.add("a")
    await f.service.sync()
    f.provider.live = {ref("a")}
    await f.kick.poll_once()
    assert f.tracker.is_live(ref("a")) is True

    await f.favorites.delete(favorite.id)
    await f.service.sync()

    assert f.tracker.is_live(ref("a")) is None


async def test_favorites_of_a_platform_without_a_monitor_are_reported_unsupported_not_failed():
    f = _Fixture(with_kick_monitor=False)
    await f.add("a")

    report = await f.service.sync()

    assert report.unsupported == (ref("a"),)
    assert report.failed == ()
    assert report.subscribed == ()


async def test_a_platform_not_registered_at_all_is_also_unsupported():
    f = _Fixture()
    f.registry = PlatformRegistry({Platform.KICK: PlatformAdapters(live_monitor=f.kick)})
    service = LiveMonitorService(
        f.favorites, f.registry, f.tracker, FakeProbe([ResourceSample(0.0, 1)])
    )
    await f.favorites.save(Favorite(channel_ref=ref("t", Platform.TWITCH)))

    report = await service.sync()

    assert report.unsupported == (ref("t", Platform.TWITCH),)


async def test_a_failing_subscribe_is_reported_and_retried_on_the_next_sync():
    f = _Fixture()
    await f.add("a")
    original = f.kick.subscribe
    calls = [0]

    async def flaky(channel_ref):
        calls[0] += 1
        if calls[0] == 1:
            raise RuntimeError("push down")
        await original(channel_ref)

    f.kick.subscribe = flaky  # type: ignore[method-assign]

    first = await f.service.sync()
    second = await f.service.sync()

    assert first.failed == ((ref("a"), "push down"),)
    assert second.subscribed == (ref("a"),)


async def test_start_runs_the_monitors_and_go_live_events_reach_the_public_bus():
    f = _Fixture()
    await f.add("a")
    f.provider.live = {ref("a")}

    report = await f.service.start()
    await asyncio.sleep(0.2)
    await f.service.stop()

    assert report.subscribed == (ref("a"),)
    online = [e for e in f.events if isinstance(e, ChannelWentOnline)]
    assert len(online) == 1
    assert online[0].initial is True


async def test_stop_leaves_no_running_tasks_and_start_is_idempotent():
    f = _Fixture()
    await f.add("a")
    await f.service.start()
    await f.service.start()  # only re-syncs
    before = len(asyncio.all_tasks())

    await f.service.stop()

    assert len(asyncio.all_tasks()) < before


async def test_metrics_report_platform_stats_and_live_channel_count():
    f = _Fixture()
    await f.add("a")
    await f.service.sync()
    f.provider.live = {ref("a")}
    await f.kick.poll_once()

    snap = f.service.metrics()

    assert snap.per_platform[Platform.KICK].requests == 1
    assert snap.total.channels_watched == 1
    assert snap.live_channels == 1
    assert snap.rss_bytes == 1_000_000


async def test_a_stopped_service_cannot_be_restarted():
    import pytest

    f = _Fixture()
    await f.service.start()
    await f.service.stop()

    with pytest.raises(RuntimeError):
        await f.service.start()
