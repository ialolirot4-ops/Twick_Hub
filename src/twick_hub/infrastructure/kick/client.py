"""Authenticated REST client for ``api.kick.com/public/v1``.

Every path here is exactly as documented/confirmed during this phase's
research (Master Plan §42: "No inventar endpoints") — see
docs/kick-audit.md for the source-by-source evidence.
"""

from __future__ import annotations

import httpx

from twick_hub.infrastructure.kick.config import API_BASE_URL
from twick_hub.infrastructure.kick.errors import KickAPIError


class KickAPIClient:
    def __init__(self, http_client: httpx.AsyncClient, access_token_getter) -> None:
        self._http = http_client
        self._get_access_token = access_token_getter

    async def get_current_user(self) -> dict:
        data = await self._get("/users")
        users = data.get("data") or []
        if not users:
            raise KickAPIError("Kick returned no user for this token.")
        return users[0]

    async def get_channel_by_slug(self, slug: str) -> dict | None:
        data = await self._get("/channels", params={"slug": slug})
        channels = data.get("data") or []
        return channels[0] if channels else None

    async def get_channel_by_broadcaster_id(self, broadcaster_user_id: str) -> dict | None:
        data = await self._get("/channels", params={"broadcaster_user_id": broadcaster_user_id})
        channels = data.get("data") or []
        return channels[0] if channels else None

    async def get_livestream(self, broadcaster_user_id: str) -> dict | None:
        data = await self._get("/livestreams", params={"broadcaster_user_id": broadcaster_user_id})
        streams = data.get("data") or []
        return streams[0] if streams else None

    async def search_categories(self, query: str) -> list[dict]:
        data = await self._get("/categories", params={"q": query})
        return data.get("data") or []

    async def _get(self, path: str, params: dict | None = None) -> dict:
        token = self._get_access_token()
        response = await self._http.get(
            f"{API_BASE_URL}{path}", params=params, headers={"Authorization": f"Bearer {token}"}
        )
        if response.status_code >= 400:
            raise KickAPIError(f"Kick API {path} returned {response.status_code}: {response.text}")
        return response.json()
