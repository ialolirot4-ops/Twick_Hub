"""App access token provider (client credentials grant).

Separate from the user's browser-session token — see
docs/architecture-decisions.md AD-04 and config.py's module docstring.
This is the credential FASE 4d's EventSub provider will use, so it has a
much larger cost budget than the user token (docs/risk-register.md
RISK-TWITCH-01).

Uses ``httpx.AsyncClient`` (never blocks the UI thread — a permanent
Master Plan rule) and takes the client as a constructor argument so
tests can supply one built on ``httpx.MockTransport`` instead of hitting
the real network (Twitch's endpoints aren't reachable from this sandbox
regardless — not in the allowed egress list this project was built
under).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from twick_hub.infrastructure.twitch.config import TOKEN_URL, TwitchAppCredentials
from twick_hub.infrastructure.twitch.errors import (
    TokenRefreshFailedError,
    TokenRevokeFailedError,
)

# Refresh this many seconds before actual expiry, so a call in flight
# doesn't race a token that expires mid-request.
_EXPIRY_SAFETY_MARGIN_SECONDS = 60


@dataclass(frozen=True, slots=True)
class AppToken:
    value: str
    expires_at: float  # time.monotonic()-based, not wall-clock — see is_valid

    def is_valid(self) -> bool:
        return time.monotonic() < (self.expires_at - _EXPIRY_SAFETY_MARGIN_SECONDS)


class AppTokenProvider:
    def __init__(self, credentials: TwitchAppCredentials, http_client: httpx.AsyncClient) -> None:
        self._credentials = credentials
        self._http = http_client
        self._cached: AppToken | None = None

    async def get_token(self) -> AppToken:
        """Returns a cached token if it's still valid, otherwise requests
        a fresh one. Callers never need to think about expiry themselves.
        """
        if self._cached is not None and self._cached.is_valid():
            return self._cached

        if not self._credentials.is_configured:
            raise TokenRefreshFailedError(
                "No Twitch app client_id/client_secret configured — "
                "see docs/architecture-decisions.md AD-04."
            )

        try:
            response = await self._http.post(
                TOKEN_URL,
                data={
                    "client_id": self._credentials.client_id,
                    "client_secret": self._credentials.client_secret,
                    "grant_type": "client_credentials",
                },
            )
            response.raise_for_status()
            payload = response.json()
            token = AppToken(
                value=payload["access_token"],
                expires_at=time.monotonic() + payload["expires_in"],
            )
        except (httpx.HTTPError, KeyError) as error:
            raise TokenRefreshFailedError(
                f"Failed to obtain an app access token: {error}"
            ) from error

        self._cached = token
        return token

    async def revoke(self) -> None:
        if self._cached is None or self._credentials.client_id is None:
            return
        try:
            response = await self._http.post(
                "https://id.twitch.tv/oauth2/revoke",
                data={"client_id": self._credentials.client_id, "token": self._cached.value},
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise TokenRevokeFailedError(str(error)) from error
        finally:
            # Same reasoning as TwitchTokenStore.delete: a failed revoke
            # call must not leave the app believing it still holds a
            # valid token.
            self._cached = None
