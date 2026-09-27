"""Keeps a long-running monitor loop alive across failures.

``TwitchEventSubProvider.run_forever`` (FASE 4d) deliberately has no
error handling of its own — a dropped socket it can't re-open just
raises. Left unsupervised, that ends the task and monitoring silently
stops for the rest of the session. ``supervise`` restarts such a loop
with exponential backoff (never a tight retry loop), and stops
restarting the moment a stop is requested.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from twick_hub.application.live_monitor.polling_policy import AdaptiveInterval, PollingConfig

logger = logging.getLogger(__name__)

SUPERVISOR_CONFIG = PollingConfig(
    base_interval=2.0,
    max_quiet_interval=2.0,
    max_backoff_interval=120.0,
)
_HEALTHY_AFTER_SECONDS = 60.0  # a run that lasted this long before failing wasn't a crash loop


async def supervise(
    name: str,
    run: Callable[[], Awaitable[None]],
    *,
    stop: asyncio.Event,
    backoff: AdaptiveInterval | None = None,
    on_error: Callable[[Exception], None] | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    backoff = backoff or AdaptiveInterval(SUPERVISOR_CONFIG)
    while not stop.is_set():
        started = clock()
        try:
            await run()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("%s crashed; restarting after backoff", name)
            if on_error is not None:
                on_error(exc)
            if clock() - started >= _HEALTHY_AFTER_SECONDS:
                backoff.reset()
            backoff.record_failure()
            try:
                await asyncio.wait_for(stop.wait(), timeout=backoff.next_delay())
            except TimeoutError:
                continue
        else:
            return  # a clean return only ever follows stop(); never restart it
