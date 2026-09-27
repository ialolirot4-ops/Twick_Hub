"""Domain-level error types shared across platform adapters.

Application code (the live monitor, FASE 10) needs to react to two
failure modes without importing any platform's own error hierarchy — that
would couple Application to Infrastructure (Master Plan §4: Domain and
Application never depend on a concrete platform). Each adapter's own
error class derives from the matching type here, so a plain
``except RateLimitedError`` works whichever platform raised it.
"""

from __future__ import annotations


class LiveMonitorCapacityError(Exception):
    """A live monitor cannot accept one more channel right now (e.g.
    Twitch EventSub's fixed cost budget, docs/risk-register.md
    RISK-TWITCH-01). Expected and recoverable — callers fall back to
    another mechanism instead of treating it as a bug.
    """


class RateLimitedError(Exception):
    """The platform answered "too many requests". ``retry_after`` is the
    number of seconds the platform asked us to wait, when it said — never
    guessed when it didn't.
    """

    def __init__(self, message: str = "rate limited", retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after
