"""Exponential backoff between attempts at one recording."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    base_delay_seconds: float = 30.0
    factor: float = 2.0
    max_delay_seconds: float = 600.0

    def delay_for(self, failed_attempts: int) -> float:
        """Seconds to wait after the ``failed_attempts``-th failure (1 = the
        first failure)."""
        if failed_attempts < 1:
            return 0.0
        return min(
            self.base_delay_seconds * self.factor ** (failed_attempts - 1), self.max_delay_seconds
        )
