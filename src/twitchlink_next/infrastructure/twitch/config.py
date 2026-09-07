"""Twitch auth configuration.

Two separate client identities, on purpose — see
docs/architecture-decisions.md AD-04:

- ``WEB_CLIENT_ID`` is Twitch's own web client ID. It's used together with
  a token extracted from the user's real browser session (not issued
  through a project-owned OAuth flow) — this is how the unofficial GQL
  API and Integrity work, and it's the same client id TwitchLink 3.5.5
  already uses (docs/migration-map.md).
- ``app_client_id``/``app_client_secret`` belong to a Twitch application
  TwitchLink Next registers for itself, used only for the app-access-token
  (client credentials) flow that FASE 4d's EventSub needs. They come from
  ``AppConfig``/environment, never hardcoded — unlike the web client id,
  which is a fixed, public value Twitch's own site uses for everyone.
"""

from __future__ import annotations

from dataclasses import dataclass

# Twitch's own web client ID — public, used by twitch.tv itself, not a
# secret. Confirmed during FASE 0's audit of TwitchLink 3.5.5
# (docs/architecture-decisions.md AD-04).
WEB_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"

VALIDATE_URL = "https://id.twitch.tv/oauth2/validate"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"
REVOKE_URL = "https://id.twitch.tv/oauth2/revoke"
INTEGRITY_URL = "https://gql.twitch.tv/integrity"
ACCOUNT_PAGE_URL = "https://www.twitch.tv/settings/account"

TOKEN_STORE_SERVICE_NAME = "TwitchLinkNext-Twitch"
USER_TOKEN_STORE_KEY = "user-session-token"


@dataclass(frozen=True, slots=True)
class TwitchAppCredentials:
    """The project's own registered Twitch application, for the
    client-credentials (app access token) flow only. ``None`` fields mean
    "not configured" — EventSub (FASE 4d) degrades to the Helix polling
    fallback from docs/risk-register.md RISK-TWITCH-01 rather than
    crashing.
    """

    client_id: str | None
    client_secret: str | None

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)
