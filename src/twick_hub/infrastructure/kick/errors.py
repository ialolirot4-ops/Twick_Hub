"""Kick error hierarchy."""

from __future__ import annotations

from twick_hub.domain.errors import RateLimitedError


class KickError(Exception):
    """Base class for every error in this package."""


class KickAuthError(KickError):
    """OAuth flow (authorize/exchange/refresh/revoke) failed."""


class NotAuthenticatedError(KickError):
    """An API call needs a signed-in Kick account and there isn't one."""


class KickDataNotFoundError(KickError):
    """The requested channel/user doesn't exist."""


class KickAPIError(KickError):
    """Kick's API returned an error response."""


class KickRateLimitedError(KickAPIError, RateLimitedError):
    """Kick answered 429. ``retry_after`` is set only when Kick sent a
    numeric ``Retry-After`` header — Kick's own rate limits are still
    unconfirmed (docs/kick-audit.md), so nothing is assumed beyond that.
    """
