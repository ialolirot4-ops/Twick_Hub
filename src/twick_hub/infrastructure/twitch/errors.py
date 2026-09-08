"""Twitch authentication error hierarchy (Master Plan §38: "errores").

Every failure mode FASE 4a needs to handle gets its own class so callers
(eventually the UI layer) can catch specifically what they know how to
recover from, instead of a bare ``except Exception``.
"""

from __future__ import annotations


class TwitchAuthError(Exception):
    """Base class for every error in this package."""


class NoBrowserSessionFoundError(TwitchAuthError):
    """No supported browser had a usable Twitch session to import."""


class TokenExpiredError(TwitchAuthError):
    """A stored token was present but Twitch no longer accepts it."""


class TokenRefreshFailedError(TwitchAuthError):
    """An app-access-token refresh (client credentials grant) failed."""


class TokenRevokeFailedError(TwitchAuthError):
    """Revoking a token with Twitch failed. The token is still deleted
    from local storage regardless — see account_service.py — since a
    failed revoke shouldn't leave the app claiming to be signed in."""


class SecureStorageUnavailableError(TwitchAuthError):
    """The OS credential store (keyring) isn't usable on this machine.

    This is a real, expected failure mode on a Linux desktop with no
    Secret Service running — not just a sandbox artifact. See
    docs/architecture-decisions.md AD-07.
    """


class IntegrityUnavailableError(TwitchAuthError):
    """Couldn't obtain a Client-Integrity token. See
    docs/risk-register.md RISK-TWITCH-04 — this is expected to happen
    periodically as Twitch changes its anti-bot checks, not a bug to
    "fix" once and forget."""
