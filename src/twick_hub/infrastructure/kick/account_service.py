"""Kick account service — implements ``domain.protocols.AccountProvider``,
the same protocol ``TwitchAccountService`` implements. Handles refresh
transparently: every call that needs a token goes through
``ensure_fresh_token``, which refreshes first if the stored token has
expired.
"""

from __future__ import annotations

import time
from datetime import datetime

from twick_hub.domain.enums import Platform
from twick_hub.domain.identity import PlatformAccount
from twick_hub.domain.value_objects import PlatformRef
from twick_hub.infrastructure.kick.client import KickAPIClient
from twick_hub.infrastructure.kick.config import TOKEN_STORE_KEY
from twick_hub.infrastructure.kick.errors import NotAuthenticatedError
from twick_hub.infrastructure.kick.mappers import map_user
from twick_hub.infrastructure.kick.oauth_flow import KickOAuthFlow
from twick_hub.infrastructure.kick.token_store import KickTokenStore

_EXPIRY_SAFETY_MARGIN_SECONDS = 60


class KickAccountService:
    def __init__(
        self, oauth_flow: KickOAuthFlow, token_store: KickTokenStore, api_client: KickAPIClient
    ) -> None:
        self._oauth = oauth_flow
        self._token_store = token_store
        self._api = api_client

    async def connect(self) -> PlatformAccount:
        tokens = await self._oauth.authorize()
        self._token_store.save(TOKEN_STORE_KEY, tokens)
        user_data = await self._api.get_current_user()
        return _account_from_user(user_data)

    async def disconnect(self) -> None:
        tokens = self._token_store.load(TOKEN_STORE_KEY)
        if tokens is not None:
            await self._oauth.revoke(tokens.access_token)
        self._token_store.delete(TOKEN_STORE_KEY)

    async def current_account(self) -> PlatformAccount | None:
        tokens = self._token_store.load(TOKEN_STORE_KEY)
        if tokens is None:
            return None
        try:
            user_data = await self._api.get_current_user()
        except Exception:
            self._token_store.delete(TOKEN_STORE_KEY)
            return None
        return _account_from_user(user_data)

    def get_access_token(self) -> str | None:
        """Synchronous accessor for ``KickAPIClient``'s
        ``access_token_getter`` — refreshing needs an awaited HTTP call,
        so it happens separately via ``ensure_fresh_token``, not here.
        """
        tokens = self._token_store.load(TOKEN_STORE_KEY)
        return tokens.access_token if tokens is not None else None

    async def ensure_fresh_token(self) -> str:
        tokens = self._token_store.load(TOKEN_STORE_KEY)
        if tokens is None:
            raise NotAuthenticatedError("No Kick account connected.")
        if tokens.expires_at - _EXPIRY_SAFETY_MARGIN_SECONDS > time.time():
            return tokens.access_token
        refreshed = await self._oauth.refresh(tokens.refresh_token)
        self._token_store.save(TOKEN_STORE_KEY, refreshed)
        return refreshed.access_token


def _account_from_user(user_data: dict) -> PlatformAccount:
    user = map_user(user_data)
    return PlatformAccount(
        ref=PlatformRef(platform=Platform.KICK, external_id=user.ref.external_id),
        username=user.username,
        connected_at=datetime.now(),
    )
