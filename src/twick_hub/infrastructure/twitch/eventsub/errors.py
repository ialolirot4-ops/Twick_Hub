"""EventSub error hierarchy."""

from __future__ import annotations


class EventSubError(Exception):
    """Base class for every error in this package."""


class CapacityExceededError(EventSubError):
    """Adding this channel would exceed the user token's cost budget
    (docs/risk-register.md RISK-TWITCH-01). Real, not a bug — see
    config.py's module docstring. Callers (FASE 10, Live Monitor) decide
    what to do about channels beyond this ceiling; this layer only
    refuses to silently over-subscribe.
    """


class SubscriptionRejectedError(EventSubError):
    """Twitch's Helix API refused to create the subscription."""


class ConnectionLostError(EventSubError):
    """The WebSocket connection dropped without a graceful
    ``session_reconnect`` — the caller must open an entirely new
    connection and recreate every subscription (they don't carry over
    on an abnormal drop, unlike a graceful reconnect)."""
