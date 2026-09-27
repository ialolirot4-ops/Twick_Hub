"""Adaptive pacing for polling monitors (Master Plan §47: "adaptativo;
backoff; agrupación cuando sea posible; reducción cuando corresponda").

Pure and deterministic: no I/O, no sleeping, no global clock. The monitor
owns the actual waiting, so tests drive this with a seeded ``rng`` and
never wait on it.

Three behaviours, in order of importance:

* **Backoff** — every consecutive failure multiplies the wait
  (``backoff_factor``), up to ``max_backoff_interval``. A ``retry_after``
  the platform sent is a hard minimum, never undercut.
* **Quiet stretch** — after ``quiet_polls_before_stretch`` consecutive
  polls that found nothing new, the interval grows gradually toward
  ``max_quiet_interval``; any change snaps it back to ``base_interval``.
  Setting ``max_quiet_interval`` equal to ``base_interval`` disables it.
* **Jitter** — the delay is stretched by a random 0-``jitter_ratio``
  fraction (never shortened, so a ``retry_after`` still holds), so many
  installs recovering from the same outage don't all retry in lockstep.

The defaults are provisional starting points, deliberately unproven: no
real platform endpoint is reachable from this project's sandbox, and
Kick's official rate limits are still unconfirmed
(docs/kick-audit.md). ``LiveMonitorMetrics`` exists to tune them.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass

_MAX_RETRY_AFTER_SECONDS = 3600.0  # a buggy server can't park a monitor for days


@dataclass(frozen=True, slots=True)
class PollingConfig:
    base_interval: float = 60.0
    quiet_polls_before_stretch: int = 5
    quiet_stretch_factor: float = 1.5
    max_quiet_interval: float = 180.0
    backoff_factor: float = 2.0
    max_backoff_interval: float = 900.0
    jitter_ratio: float = 0.1
    coalesce_seconds: float = 1.0  # how long to let a burst of subscribes settle before polling

    def __post_init__(self) -> None:
        if self.base_interval <= 0:
            raise ValueError("base_interval must be > 0")
        if self.max_quiet_interval < self.base_interval:
            raise ValueError("max_quiet_interval must be >= base_interval")
        if self.max_backoff_interval < self.base_interval:
            raise ValueError("max_backoff_interval must be >= base_interval")
        if self.quiet_stretch_factor < 1 or self.backoff_factor < 1:
            raise ValueError("stretch/backoff factors must be >= 1")
        if self.quiet_polls_before_stretch < 1:
            raise ValueError("quiet_polls_before_stretch must be >= 1")
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be within [0, 1]")
        if self.coalesce_seconds < 0:
            raise ValueError("coalesce_seconds must be >= 0")


class AdaptiveInterval:
    def __init__(
        self, config: PollingConfig | None = None, rng: Callable[[], float] = random.random
    ) -> None:
        self._config = config or PollingConfig()
        self._rng = rng
        self._interval = self._config.base_interval
        self._quiet_streak = 0
        self._failures = 0

    @property
    def config(self) -> PollingConfig:
        return self._config

    @property
    def current_interval(self) -> float:
        """The interval before jitter."""
        return self._interval

    @property
    def consecutive_failures(self) -> int:
        return self._failures

    def record_success(self, *, changed: bool) -> None:
        config = self._config
        recovering = self._failures > 0
        self._failures = 0
        if changed or recovering:
            # News, or the first good answer after an outage: back to the
            # normal cadence rather than staying at a backed-off one.
            self._quiet_streak = 0
            self._interval = config.base_interval
            return
        self._quiet_streak += 1
        if self._quiet_streak >= config.quiet_polls_before_stretch:
            self._interval = min(
                self._interval * config.quiet_stretch_factor, config.max_quiet_interval
            )

    def record_failure(self, retry_after: float | None = None) -> None:
        config = self._config
        self._failures += 1
        self._quiet_streak = 0
        interval = min(
            config.base_interval * config.backoff_factor**self._failures,
            config.max_backoff_interval,
        )
        if retry_after is not None:
            interval = max(interval, min(retry_after, _MAX_RETRY_AFTER_SECONDS))
        self._interval = interval

    def next_delay(self) -> float:
        return self._interval * (1 + self._config.jitter_ratio * self._rng())

    def reset(self) -> None:
        self._interval = self._config.base_interval
        self._quiet_streak = 0
        self._failures = 0
