"""Twitch account service — implements ``domain.protocols.AccountProvider``.

Uses only the official, documented ``/oauth2/validate`` endpoint to learn
who a token belongs to (Master Plan §38: "No implementar GraphQL completo
todavía" — the full GQL client is FASE 4b).
"""

from __future__ import annotations

import contextlib
from datetime import datetime

import httpx

from twick_hub.domain.enums import Platform
from twick_hub.domain.identity import PlatformAccount
from twick_hub.domain.value_objects import PlatformRef
from twick_hub.infrastructure.twitch.browser_cookie_import import CookieImporter
from twick_hub.infrastructure.twitch.config import (
    USER_TOKEN_STORE_KEY,
    VALIDATE_URL,
    WEB_CLIENT_ID,
)
from twick_hub.infrastructure.twitch.errors import (
    NoBrowserSessionFoundError,
    TokenExpiredError,
)
from twick_hub.infrastructure.twitch.token_store import TwitchTokenStore


class TwitchAccountService:
    def __init__(
        self,
        cookie_importer: CookieImporter,
        token_store: TwitchTokenStore,
        http_client: httpx.AsyncClient,
    ) -> None:
        self._cookie_importer = cookie_importer
        self._token_store = token_store
        self._http = http_client

    async def connect(self) -> PlatformAccount:
        profiles = self._cookie_importer.list_profiles()
        if not profiles:
            raise NoBrowserSessionFoundError("No Firefox profile found to import a session from.")

        # FASE 4a scope: use the first profile found. Picking among
        # several is a UI concern (Account page), not this service's job.
        token = self._cookie_importer.import_session_token(profiles[0])
        validation = await self._validate(token)

        self._token_store.save(USER_TOKEN_STORE_KEY, token)
        return self._account_from_validation(validation)

    async def disconnect(self) -> None:
        token = self._token_store.load(USER_TOKEN_STORE_KEY)
        if token:
            # A failed server-side revoke must not block local sign-out —
            # same reasoning as AppTokenProvider.revoke.
            with contextlib.suppress(httpx.HTTPError):
                await self._http.post(
                    "https://id.twitch.tv/oauth2/revoke",
                    data={"client_id": WEB_CLIENT_ID, "token": token},
                )
        self._token_store.delete(USER_TOKEN_STORE_KEY)

    async def current_account(self) -> PlatformAccount | None:
        token = self._token_store.load(USER_TOKEN_STORE_KEY)
        if token is None:
            return None
        try:
            validation = await self._validate(token)
        except TokenExpiredError:
            self._token_store.delete(USER_TOKEN_STORE_KEY)
            return None
        return self._account_from_validation(validation)

    async def _validate(self, token: str) -> dict:
        response = await self._http.get(VALIDATE_URL, headers={"Authorization": f"OAuth {token}"})
        if response.status_code == 401:
            raise TokenExpiredError("Twitch no longer accepts this session token.")
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _account_from_validation(validation: dict) -> PlatformAccount:
        return PlatformAccount(
            ref=PlatformRef(platform=Platform.TWITCH, external_id=validation["user_id"]),
            username=validation["login"],
            connected_at=datetime.now(),
        )
