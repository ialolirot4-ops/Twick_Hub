"""Adaptive polling live monitor — implements ``domain.protocols.LiveMonitor``.

Kick has no push transport this project can use (docs/architecture-
decisions.md AD-06; webhooks need a public endpoint and their delivery is
unreliable per KickDevDocs #300/#367), and Twitch's EventSub covers at
most 5 channels per token (RISK-TWITCH-01). This is the backend for both
situations: it asks a ``BatchLiveStatusProvider`` about *all* watched
channels at once (one request per API chunk, not one per channel) and
reports what it saw to a ``LiveObserver``.

Costs nothing while idle: with no channel watched, the loop parks on an
``asyncio.Event`` — no timer, no request — until ``subscribe`` wakes it.

``poll_once`` is the unit of work, separate from ``run_forever`` — same
pattern as ``TwitchEventSubProvider._receive_and_handle_one`` (AD-25) —
so tests drive one poll deterministically instead of racing a task.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Callable

from twick_hub.application.live_monitor.polling_policy import AdaptiveInterval, PollingConfig
from twick_hub.application.live_monitor.tracker import LiveObserver
from twick_hub.domain.errors import RateLimitedError
from twick_hub.domain.monitoring import MonitorStats
from twick_hub.domain.protocols import BatchLiveStatusProvider
from twick_hub.domain.value_objects import PlatformRef

logger = logging.getLogger(__name__)


class PollingLiveMonitor:
    def __init__(
        self,
        provider: BatchLiveStatusProvider,
        observer: LiveObserver,
        *,
        config: PollingConfig | None = None,
        label: str = "polling",
        rng: Callable[[], float] = random.random,
    ) -> None:
        self._provider = provider
        self._observer = observer
        self._label = label
        self._policy = AdaptiveInterval(config, rng)
        self._watched: dict[PlatformRef, None] = {}  # insertion-ordered set
        self._wakeup = asyncio.Event()
        self._stopped = False

        self._requests = 0
        self._polls = 0
        self._errors = 0
        self._rate_limited = 0

    # --- LiveMonitor -------------------------------------------------

    async def subscribe(self, channel_ref: PlatformRef) -> None:
        if channel_ref in self._watched:
            return
        self._watched[channel_ref] = None
        self._wakeup.set()  # a channel we know nothing about yet shouldn't wait a full interval

    async def unsubscribe(self, channel_ref: PlatformRef) -> None:
        self._watched.pop(channel_ref, None)

    # --- introspection -----------------------------------------------

    @property
    def watched(self) -> frozenset[PlatformRef]:
        return frozenset(self._watched)

    @property
    def current_interval(self) -> float:
        return self._policy.current_interval

    def stats(self) -> MonitorStats:
        return MonitorStats(
            requests=self._requests,
            polls=self._polls,
            errors=self._errors,
            rate_limited=self._rate_limited,
            channels_watched=len(self._watched),
            poll_interval_seconds=self._policy.current_interval if self._watched else 0.0,
        )

    # --- work --------------------------------------------------------

    async def poll_once(self) -> None:
        """One poll of every watched channel. Never raises for a platform
        failure: it is counted, the pacing backs off, and the next
        scheduled poll retries. (Cancellation still propagates.)"""
        snapshot = list(self._watched)
        if not snapshot:
            return
        try:
            batch = await self._provider.get_live_streams(snapshot)
        except asyncio.CancelledError:
            raise
        except RateLimitedError as exc:
            self._errors += 1
            self._rate_limited += 1
            self._policy.record_failure(exc.retry_after)
            logger.warning("%s: rate limited (retry_after=%s)", self._label, exc.retry_after)
            return
        except Exception as exc:
            self._errors += 1
            self._policy.record_failure()
            logger.warning("%s: poll failed: %s", self._label, exc)
            return

        self._requests += batch.requests_made
        self._polls += 1
        changed = False
        for channel_ref in snapshot:
            if channel_ref not in self._watched:
                continue  # unsubscribed while the request was in flight
            stream = batch.live.get(channel_ref)
            if stream is not None:
                news = await self._observer.observe_live(channel_ref, stream)
            else:
                news = await self._observer.observe_offline(channel_ref)
            changed = changed or news
        self._policy.record_success(changed=changed)

    async def run_forever(self) -> None:
        while not self._stopped:
            # With nothing to watch there is no timeout at all — the loop
            # parks until a subscription (or stop) wakes it.
            timeout = self._policy.next_delay() if self._watched else None
            woken = await self._wait(timeout)
            if self._stopped:
                break
            if woken:
                # New channels (or a burst of them) — poll soon rather
                # than after a full interval, but let the burst settle so
                # N subscribes cost one request, not N.
                await asyncio.sleep(self._policy.config.coalesce_seconds)
                # The poll below covers everything subscribed so far, so
                # wake-ups that arrived during the pause are already served.
                self._wakeup.clear()
            await self.poll_once()

    async def stop(self) -> None:
        self._stopped = True
        self._wakeup.set()

    # --- waiting -----------------------------------------------------

    async def _wait(self, timeout: float | None) -> bool:
        """True if woken (subscribe/stop) before ``timeout`` elapsed. A
        wake that happened before this call still counts: a channel
        subscribed before ``run_forever`` started is polled promptly."""
        try:
            await asyncio.wait_for(self._wakeup.wait(), timeout=timeout)
        except TimeoutError:
            return False
        self._wakeup.clear()
        return True
