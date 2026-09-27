"""Authenticated REST client for ``api.kick.com/public/v1``.

Every path here is exactly as documented/confirmed during this phase's
research (Master Plan §42: "No inventar endpoints") — see
docs/kick-audit.md for the source-by-source evidence.
"""

from __future__ import annotations

from collections.abc import Sequence

import httpx

from twick_hub.infrastructure.kick.config import API_BASE_URL
from twick_hub.infrastructure.kick.errors import KickAPIError, KickRateLimitedError


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

    async def get_livestreams(self, broadcaster_user_ids: Sequence[str]) -> list[dict]:
        """Live streams among ``broadcaster_user_ids``. Kick's changelog
        (KickDevDocs, 28/07/2025, "Allow multiple broadcaster_user_id
        params on livestreams") means the wire format is the *same*
        ``broadcaster_user_id`` key repeated, one per id — not a
        comma-separated list, and not the ``broadcaster_user_ids`` name some
        SDKs use for their own argument. Up to 50 per request (per the SDKs
        that document it); callers chunk. Channels that aren't live are
        simply absent from the result.
        """
        if not broadcaster_user_ids:
            return []
        data = await self._get(
            "/livestreams", params={"broadcaster_user_id": list(broadcaster_user_ids)}
        )
        return data.get("data") or []

    async def search_categories(self, query: str) -> list[dict]:
        data = await self._get("/categories", params={"q": query})
        return data.get("data") or []

    async def _get(self, path: str, params: dict | None = None) -> dict:
        token = self._get_access_token()
        response = await self._http.get(
            f"{API_BASE_URL}{path}", params=params, headers={"Authorization": f"Bearer {token}"}
        )
        if response.status_code == 429:
            raise KickRateLimitedError(
                f"Kick API {path} returned 429: {response.text}",
                retry_after=_retry_after_seconds(response),
            )
        if response.status_code >= 400:
            raise KickAPIError(f"Kick API {path} returned {response.status_code}: {response.text}")
        return response.json()


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """Numeric ``Retry-After`` only. The header may also be an HTTP-date;
    nothing here relies on Kick sending either form, so an unparseable
    value is reported as "not given" instead of guessed at."""
    raw = response.headers.get("retry-after")
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None
