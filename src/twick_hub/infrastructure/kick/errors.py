"""Kick error hierarchy."""

from __future__ import annotations


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
