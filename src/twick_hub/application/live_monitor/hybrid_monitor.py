"""One platform's live monitor built from a push backend plus two
pollers — implements ``domain.protocols.LiveMonitor``.

Master Plan §47: "Preferir push/eventos oficiales antes que polling."
Twitch's EventSub is the push backend, but a user token gets a fixed cost
budget of 10 — exactly 5 channels (RISK-TWITCH-01). Three roles result:

* **push** (``primary``): the first channels that fit, in the order they
  were subscribed. Costs no polling requests at all.
* **reconcile** (slow poller, same channels as push): push tells you
  about *transitions* only, and not the initial state, anything lost
  while a socket was down, or an online notification whose details
  couldn't be fetched. One cheap batched request every ~15 minutes closes
  all three gaps.
* **fallback** (fast poller): every channel that didn't fit in push.

When a push slot frees up (a favorite was removed), the oldest fallback
channel is promoted into it, so polling shrinks back as capacity returns.
A channel whose push subscription is revoked by the platform is demoted
to fallback rather than silently going unmonitored.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from typing import Any

from twick_hub.application.live_monitor.polling_monitor import PollingLiveMonitor
from twick_hub.application.live_monitor.supervision import supervise
from twick_hub.domain.errors import LiveMonitorCapacityError
from twick_hub.domain.monitoring import (
    MonitorRunner,
    MonitorStats,
    MonitorStatsSource,
    PushLossNotifier,
)
from twick_hub.domain.protocols import LiveMonitor
from twick_hub.domain.value_objects import PlatformRef

logger = logging.getLogger(__name__)


class HybridLiveMonitor:
    def __init__(
        self,
        primary: LiveMonitor,
        fallback: PollingLiveMonitor,
        reconciler: PollingLiveMonitor,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._reconciler = reconciler
        self._push: dict[PlatformRef, None] = {}
        self._polled: dict[PlatformRef, None] = {}
        self._own_errors = 0
        self._stop = asyncio.Event()
        self._background: set[asyncio.Task[Any]] = set()
        if isinstance(primary, PushLossNotifier):
            primary.on_push_lost(self._on_push_lost)

    # --- LiveMonitor -------------------------------------------------

    async def subscribe(self, channel_ref: PlatformRef) -> None:
        if channel_ref in self._push or channel_ref in self._polled:
            return
        if await self._try_push(channel_ref):
            return
        self._polled[channel_ref] = None
        await self._fallback.subscribe(channel_ref)

    async def unsubscribe(self, channel_ref: PlatformRef) -> None:
        if channel_ref in self._polled:
            del self._polled[channel_ref]
            await self._fallback.unsubscribe(channel_ref)
            return
        if channel_ref not in self._push:
            return
        del self._push[channel_ref]
        await self._reconciler.unsubscribe(channel_ref)
        try:
            await self._primary.unsubscribe(channel_ref)
        except Exception:
            self._own_errors += 1
            logger.warning("push unsubscribe failed for %s", channel_ref, exc_info=True)
        await self._promote_polled()

    # --- introspection -----------------------------------------------

    @property
    def push_channels(self) -> frozenset[PlatformRef]:
        return frozenset(self._push)

    @property
    def polled_channels(self) -> frozenset[PlatformRef]:
        return frozenset(self._polled)

    def stats(self) -> MonitorStats:
        total = self._fallback.stats() + self._reconciler.stats()
        if isinstance(self._primary, MonitorStatsSource):
            total = total + self._primary.stats()
        return dataclasses.replace(
            total,
            errors=total.errors + self._own_errors,
            # The reconciler watches the push channels a second time, and
            # the primary counts them again: report distinct channels.
            channels_watched=len(self._push) + len(self._polled),
        )

    # --- running -----------------------------------------------------

    async def run_forever(self) -> None:
        runners: list[tuple[str, MonitorRunner]] = [
            ("fallback poller", self._fallback),
            ("reconcile poller", self._reconciler),
        ]
        if isinstance(self._primary, MonitorRunner):
            runners.insert(0, ("push monitor", self._primary))
        async with asyncio.TaskGroup() as group:
            for name, runner in runners:
                group.create_task(
                    supervise(name, runner.run_forever, stop=self._stop, on_error=self._count_error)
                )

    async def stop(self) -> None:
        self._stop.set()
        for runner in (self._primary, self._fallback, self._reconciler):
            if isinstance(runner, MonitorRunner):
                await runner.stop()

    # --- internals ---------------------------------------------------

    def _count_error(self, _exc: Exception) -> None:
        self._own_errors += 1

    async def _try_push(self, channel_ref: PlatformRef) -> bool:
        try:
            await self._primary.subscribe(channel_ref)
        except LiveMonitorCapacityError:
            return False  # expected once the push budget is spent
        except asyncio.CancelledError:
            raise
        except Exception:
            self._own_errors += 1
            logger.warning("push subscribe failed for %s; polling it", channel_ref, exc_info=True)
            return False
        self._push[channel_ref] = None
        await self._reconciler.subscribe(channel_ref)
        return True

    async def _promote_polled(self) -> None:
        for channel_ref in list(self._polled):
            if not await self._try_push(channel_ref):
                break  # no room (or push is failing): stop asking
            del self._polled[channel_ref]
            await self._fallback.unsubscribe(channel_ref)

    def _on_push_lost(self, channel_ref: PlatformRef) -> None:
        if channel_ref not in self._push:
            return
        task = asyncio.get_running_loop().create_task(self._demote(channel_ref))
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def _demote(self, channel_ref: PlatformRef) -> None:
        if channel_ref not in self._push:
            return  # already handled (Twitch revokes online and offline separately)
        del self._push[channel_ref]
        self._polled[channel_ref] = None
        await self._fallback.subscribe(channel_ref)
        await self._reconciler.unsubscribe(channel_ref)
        try:
            await self._primary.unsubscribe(channel_ref)  # frees its reserved budget
        except Exception:
            self._own_errors += 1
            logger.warning("cleanup after push loss failed for %s", channel_ref, exc_info=True)
        logger.warning("push coverage lost for %s; now polled", channel_ref)
