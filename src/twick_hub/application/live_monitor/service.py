"""Keeps the platform monitors watching exactly the favorites that need
watching (Master Plan §47, FASE 10).

A favorite needs watching when its ``NotificationRule`` or its
``AutoDownloadRule`` is enabled. A favorite with both off costs nothing —
the cheapest request is the one never made (Master Plan §7). Anything else
that needs a channel watched (the scheduler's armed items) is supplied as
``extra_demand`` and simply unioned in.

The service only *coordinates*: which channel goes to which platform's
monitor, and running those monitors. It does not decide push vs polling
(each platform's ``LiveMonitor`` does), and it publishes nothing — the
``LiveStateTracker`` is the only publisher of go-live / go-offline events.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field

from twick_hub.application.live_monitor.metrics import (
    LiveMonitorMetrics,
    LiveMonitorSnapshot,
    ResourceProbe,
)
from twick_hub.application.live_monitor.supervision import supervise
from twick_hub.application.live_monitor.tracker import LiveStateTracker
from twick_hub.application.platform_registry import PlatformRegistry
from twick_hub.domain.enums import Platform
from twick_hub.domain.monitoring import MonitorRunner, MonitorStatsSource
from twick_hub.domain.protocols import FavoriteRepository
from twick_hub.domain.scheduling import AutoDownloadRule, NotificationRule
from twick_hub.domain.value_objects import PlatformRef

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SyncReport:
    subscribed: tuple[PlatformRef, ...] = ()
    unsubscribed: tuple[PlatformRef, ...] = ()
    #: Channels whose platform has no live monitor at all — not an error, just
    #: an unsupported capability (Master Plan §9), surfaced so callers can say so.
    unsupported: tuple[PlatformRef, ...] = ()
    #: (channel, reason). Not recorded as subscribed, so the next ``sync`` retries.
    failed: tuple[tuple[PlatformRef, str], ...] = field(default=())


class LiveMonitorService:
    def __init__(
        self,
        favorites: FavoriteRepository,
        registry: PlatformRegistry,
        tracker: LiveStateTracker,
        probe: ResourceProbe,
        extra_demand: Callable[[], Awaitable[Iterable[PlatformRef]]] | None = None,
    ) -> None:
        self._extra_demand = extra_demand
        self._favorites = favorites
        self._registry = registry
        self._tracker = tracker
        self._subscribed: dict[Platform, dict[PlatformRef, None]] = {}
        self._stop = asyncio.Event()
        self._stopped = False
        self._tasks: list[asyncio.Task[None]] = []
        self._metrics = LiveMonitorMetrics(
            sources=self._stat_sources,
            live_channel_count=lambda: len(tracker.live_channels),
            probe=probe,
        )

    async def sync(self) -> SyncReport:
        """Reconciles what the monitors watch with the favorites now in
        the repository. Safe to call repeatedly — after a favorite is
        added, removed, or has its notification/auto-download flags
        changed."""
        favorites = await self._favorites.list_all()
        desired: dict[Platform, dict[PlatformRef, None]] = {}
        for favorite in favorites:  # already in position order: earlier favorites win push slots
            wanted = (
                NotificationRule.from_favorite(favorite).enabled
                or AutoDownloadRule.from_favorite(favorite).enabled
            )
            if wanted:
                desired.setdefault(favorite.channel_ref.platform, {})[favorite.channel_ref] = None
        if self._extra_demand is not None:  # channels other parts of the app need watched
            for channel_ref in await self._extra_demand():
                desired.setdefault(channel_ref.platform, {}).setdefault(channel_ref, None)

        subscribed: list[PlatformRef] = []
        unsubscribed: list[PlatformRef] = []
        unsupported: list[PlatformRef] = []
        failed: list[tuple[PlatformRef, str]] = []

        for platform in Platform:
            wanted = desired.get(platform, {})
            current = self._subscribed.setdefault(platform, {})
            monitor = self._monitor_for(platform)
            if monitor is None:
                unsupported.extend(wanted)
                continue

            for channel_ref in [ref for ref in current if ref not in wanted]:
                try:
                    await monitor.unsubscribe(channel_ref)
                except Exception as exc:
                    logger.warning("unsubscribe failed for %s", channel_ref, exc_info=True)
                    failed.append((channel_ref, f"unsubscribe: {exc}"))
                    continue
                del current[channel_ref]
                self._tracker.forget(channel_ref)
                unsubscribed.append(channel_ref)

            for channel_ref in wanted:
                if channel_ref in current:
                    continue
                try:
                    await monitor.subscribe(channel_ref)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning("subscribe failed for %s", channel_ref, exc_info=True)
                    failed.append((channel_ref, str(exc)))
                    continue
                current[channel_ref] = None
                subscribed.append(channel_ref)

        return SyncReport(
            subscribed=tuple(subscribed),
            unsubscribed=tuple(unsubscribed),
            unsupported=tuple(unsupported),
            failed=tuple(failed),
        )

    async def start(self) -> SyncReport:
        """Subscribes the current favorites and starts every monitor's
        loop. Calling it again while running only re-syncs."""
        if self._stopped:
            raise RuntimeError("LiveMonitorService was stopped; build a new one to run again")
        report = await self.sync()
        if not self._tasks:
            for platform in Platform:
                monitor = self._monitor_for(platform)
                if isinstance(monitor, MonitorRunner):
                    name = f"{platform.value} live monitor"
                    self._tasks.append(
                        asyncio.create_task(supervise(name, monitor.run_forever, stop=self._stop))
                    )
        return report

    async def stop(self) -> None:
        """Terminal: monitors stop for good (a stopped monitor instance
        does not restart). Build a new service to run again."""
        self._stopped = True
        self._stop.set()
        for platform in Platform:
            monitor = self._monitor_for(platform)
            if isinstance(monitor, MonitorRunner):
                await monitor.stop()
        tasks, self._tasks = self._tasks, []
        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=5)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    def metrics(self) -> LiveMonitorSnapshot:
        return self._metrics.snapshot()

    # --- internals ---------------------------------------------------

    def _monitor_for(self, platform: Platform):
        if not self._registry.is_registered(platform):
            return None
        return self._registry.get_platform(platform).live_monitor

    def _stat_sources(self) -> Mapping[Platform, MonitorStatsSource]:
        sources: dict[Platform, MonitorStatsSource] = {}
        for platform in Platform:
            monitor = self._monitor_for(platform)
            if isinstance(monitor, MonitorStatsSource):
                sources[platform] = monitor
        return sources
