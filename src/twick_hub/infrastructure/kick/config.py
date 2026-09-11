"""Kick OAuth + API configuration.

Every URL and parameter name here is copied from Kick's own
``KickEngineering/KickDevDocs`` repository
(getting-started/generating-tokens-oauth2-flow.md), fetched during this
phase — not invented, not guessed (Master Plan §42: "No inventar
endpoints").
"""

from __future__ import annotations

from dataclasses import dataclass

OAUTH_HOST = "https://id.kick.com"
AUTHORIZE_URL = f"{OAUTH_HOST}/oauth/authorize"
# Same endpoint for auth-code exchange, refresh, and client-credentials.
TOKEN_URL = f"{OAUTH_HOST}/oauth/token"
REVOKE_URL = f"{OAUTH_HOST}/oauth/revoke"
INTROSPECT_URL = f"{OAUTH_HOST}/oauth/token/introspect"

API_BASE_URL = "https://api.kick.com/public/v1"

# Kick's own documented workaround: NextJS mangles a literal "127.0.0.1"
# redirect_uri, so "localhost" is what they recommend for a locally-run
# app's callback.
DEFAULT_REDIRECT_HOST = "localhost"
# Arbitrary, unassigned port — must match the app's registered redirect_uri exactly.
DEFAULT_REDIRECT_PORT = 51823
DEFAULT_REDIRECT_PATH = "/callback"

TOKEN_STORE_SERVICE_NAME = "TwickHub-Kick"
TOKEN_STORE_KEY = "user-tokens"

# Confirmed official webhook event types (docs.kick.com / KickDevDocs, via
# the Go and C# SDKs' own EventType enums — cross-checked against two
# independent sources during this phase's research). Documented here per
# Master Plan §42 ("eventos disponibles") — not subscribed to. AD-06
# already chose adaptive polling over webhooks for live monitoring, and
# real, current bug reports (KickDevDocs issues #300, #367) show webhook
# delivery is unreliable in practice even when correctly configured —
# see docs/kick-audit.md.
OFFICIAL_EVENT_TYPES = (
    "chat.message.sent",
    "channel.followed",
    "channel.subscription.renewal",
    "channel.subscription.gifts",
    "channel.subscription.new",
    "livestream.status.updated",
)


@dataclass(frozen=True, slots=True)
class KickAppCredentials:
    """The project's registered Kick application. Kick's token endpoint
    requires client_secret even for the PKCE authorization-code flow
    (confirmed from their own docs) — unusual for PKCE, whose point is
    normally to avoid a client secret for public/native clients, but
    it's how Kick's API is actually specified, not a choice made here.
    """

    client_id: str | None
    client_secret: str | None

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    @property
    def redirect_uri(self) -> str:
        return f"http://{DEFAULT_REDIRECT_HOST}:{DEFAULT_REDIRECT_PORT}{DEFAULT_REDIRECT_PATH}"
