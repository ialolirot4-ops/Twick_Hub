"""Twitch GQL error hierarchy — separate from
``infrastructure.twitch.errors`` (auth-specific), same "one class per
failure mode" reasoning.
"""

from __future__ import annotations


class TwitchGQLError(Exception):
    """Base class for every error in this package."""


class TwitchDataNotFoundError(TwitchGQLError):
    """The requested channel/video/clip doesn't exist (or Twitch
    returned its "id": "0" placeholder for a missing user — ported from
    TwitchGQLAPI.py's ``_raiseIfNone``)."""


class TwitchIntegrityCheckFailedError(TwitchGQLError):
    """GQL responded with the literal "failed integrity check" error —
    the cached Client-Integrity token needs refreshing. See
    docs/risk-register.md RISK-TWITCH-04."""


class TwitchGQLRequestError(TwitchGQLError):
    """The HTTP request itself failed, or the response wasn't the JSON
    shape a GQL response should have."""
