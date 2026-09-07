"""Playback error hierarchy. One class per real, meaningful condition —
ported from TwitchLink 3.5.5's ``TwitchPlaybackGenerator.py`` Exceptions,
which already distinguished these precisely.
"""

from __future__ import annotations


class TwitchPlaybackError(Exception):
    """Base class for every error in this package."""


class ChannelOfflineError(TwitchPlaybackError):
    """The channel has no active stream — a normal, expected state, not
    a failure to route to an error-reporting flow."""


class SubscriberOnlyRestrictedError(TwitchPlaybackError):
    """Ported from ``_validateToken``: the playback token's own
    ``authorization.reason`` was literally ``"UNAUTHORIZED_ENTITLMENTS"``
    — Twitch's own signal for "this needs a subscription you don't have."
    This directly answers docs/functional-baseline.md's open question on
    subscriber-only videos: it's this exact, named condition.
    """


class GeoBlockedError(TwitchPlaybackError):
    pass


class PlaybackForbiddenError(TwitchPlaybackError):
    """Any other ``authorization.forbidden`` reason Twitch might return —
    kept generic on purpose since 3.5.5 only special-cases the
    subscriber-only one, and inventing meaning for other reason strings
    Twitch might send wouldn't be verified information (Master Plan
    §36 permanent rule: no asumir).
    """

    def __init__(self, reason: str | None) -> None:
        super().__init__(reason or "forbidden")
        self.reason = reason
