"""Decides whether/when to retry a failed segment or job attempt. Pure,
deterministic logic — no I/O, no sleeping itself. ``SegmentManager``/
``DownloadExecutor`` own the actual ``await sleep(...)`` call so tests can
inject an instant sleep instead of really waiting on backoff delays.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.base_delay_seconds < 0:
            raise ValueError("base_delay_seconds must be >= 0")

    def should_retry(self, attempt: int) -> bool:
        """``attempt`` is 1-based: the attempt that just failed. Returns
        whether a further attempt is allowed."""
        return attempt < self.max_attempts

    def delay_for(self, attempt: int) -> float:
        """Exponential backoff, capped at ``max_delay_seconds``. ``attempt``
        is 1-based (the attempt that just failed; this is the delay before
        the *next* one)."""
        delay = self.base_delay_seconds * (2 ** (attempt - 1))
        return min(delay, self.max_delay_seconds)
