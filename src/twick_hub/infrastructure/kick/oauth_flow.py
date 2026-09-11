"""Kick's OAuth 2.1 + PKCE flow, end to end. Every request shape here
matches ``KickEngineering/KickDevDocs``'s own
generating-tokens-oauth2-flow.md, fetched during this phase.
"""

from __future__ import annotations

import time
import webbrowser
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from twick_hub.infrastructure.kick.config import (
    AUTHORIZE_URL,
    INTROSPECT_URL,
    REVOKE_URL,
    TOKEN_URL,
    KickAppCredentials,
)
from twick_hub.infrastructure.kick.errors import KickAuthError
from twick_hub.infrastructure.kick.pkce import generate_pkce_pair, generate_state
from twick_hub.infrastructure.kick.redirect_listener import RedirectListener
from twick_hub.infrastructure.kick.token_store import StoredKickTokens

DEFAULT_SCOPES = ("user:read", "channel:read", "events:subscribe")


@dataclass(frozen=True, slots=True)
class TokenIntrospection:
    active: bool
    scope: str | None = None
    expires_at: float | None = None


class KickOAuthFlow:
    def __init__(
        self,
        credentials: KickAppCredentials,
        http_client: httpx.AsyncClient,
        redirect_listener: RedirectListener,
        *,
        open_browser=webbrowser.open,
        scopes: tuple[str, ...] = DEFAULT_SCOPES,
    ) -> None:
        self._credentials = credentials
        self._http = http_client
        self._redirect_listener = redirect_listener
        self._open_browser = open_browser
        self._scopes = scopes

    async def authorize(self) -> StoredKickTokens:
        """Runs the full interactive flow: open the browser, wait for
        the redirect, exchange the code for tokens."""
        if not self._credentials.is_configured:
            raise KickAuthError("No Kick app client_id/client_secret configured.")

        pkce = generate_pkce_pair()
        state = generate_state()
        params = {
            "response_type": "code",
            "client_id": self._credentials.client_id,
            "redirect_uri": self._credentials.redirect_uri,
            "scope": " ".join(self._scopes),
            "state": state,
            "code_challenge": pkce.challenge,
            "code_challenge_method": "S256",
        }
        self._open_browser(f"{AUTHORIZE_URL}?{urlencode(params)}")

        code, returned_state = await self._redirect_listener.wait_for_callback(timeout=120)
        if returned_state != state:
            raise KickAuthError("OAuth state mismatch — possible CSRF, aborting sign-in.")

        return await self._exchange_code(code, pkce.verifier)

    async def _exchange_code(self, code: str, code_verifier: str) -> StoredKickTokens:
        response = await self._http.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": self._credentials.client_id,
                "client_secret": self._credentials.client_secret,
                "redirect_uri": self._credentials.redirect_uri,
                "code_verifier": code_verifier,
            },
        )
        return self._tokens_from_response(response, "exchange the authorization code")

    async def refresh(self, refresh_token: str) -> StoredKickTokens:
        response = await self._http.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self._credentials.client_id,
                "client_secret": self._credentials.client_secret,
            },
        )
        return self._tokens_from_response(response, "refresh the access token")

    async def revoke(self, token: str, *, token_hint_type: str = "access_token") -> None:
        response = await self._http.post(
            REVOKE_URL, params={"token": token, "token_hint_type": token_hint_type}
        )
        if response.status_code >= 400:
            raise KickAuthError(f"Failed to revoke token: {response.text}")

    async def introspect(self, access_token: str) -> TokenIntrospection:
        response = await self._http.post(
            INTROSPECT_URL, headers={"Authorization": f"Bearer {access_token}"}
        )
        if response.status_code >= 400:
            return TokenIntrospection(active=False)
        data = response.json().get("data", {})
        return TokenIntrospection(
            active=bool(data.get("active")), scope=data.get("scope"), expires_at=data.get("exp")
        )

    def _tokens_from_response(self, response: httpx.Response, action: str) -> StoredKickTokens:
        if response.status_code >= 400:
            raise KickAuthError(f"Failed to {action}: {response.text}")
        payload = response.json()
        try:
            return StoredKickTokens(
                access_token=payload["access_token"],
                refresh_token=payload["refresh_token"],
                expires_at=time.time() + payload["expires_in"],
            )
        except KeyError as error:
            raise KickAuthError(f"Unexpected token response shape: missing {error}") from error
