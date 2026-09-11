from __future__ import annotations

import httpx
import pytest

from twick_hub.infrastructure.kick.client import KickAPIClient
from twick_hub.infrastructure.kick.errors import KickAPIError


def _client(handler) -> KickAPIClient:
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return KickAPIClient(http_client, lambda: "access-token-1")


async def test_get_current_user_uses_bearer_auth_and_the_users_endpoint():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/public/v1/users"
        assert request.headers["authorization"] == "Bearer access-token-1"
        return httpx.Response(200, json={"data": [{"user_id": 1, "name": "someone"}]})

    user = await _client(handler).get_current_user()
    assert user["name"] == "someone"


async def test_get_current_user_with_no_data_raises():
    client = _client(lambda r: httpx.Response(200, json={"data": []}))
    with pytest.raises(KickAPIError):
        await client.get_current_user()


async def test_get_channel_by_slug_passes_slug_param():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/public/v1/channels"
        assert request.url.params["slug"] == "xqc"
        return httpx.Response(200, json={"data": [{"broadcaster_user_id": 1, "slug": "xqc"}]})

    channel = await _client(handler).get_channel_by_slug("xqc")
    assert channel is not None
    assert channel["slug"] == "xqc"


async def test_get_channel_by_slug_not_found_returns_none():
    client = _client(lambda r: httpx.Response(200, json={"data": []}))
    assert await client.get_channel_by_slug("nope") is None


async def test_get_livestream_passes_broadcaster_id():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/public/v1/livestreams"
        assert request.url.params["broadcaster_user_id"] == "42"
        return httpx.Response(200, json={"data": [{"broadcaster_user_id": 42}]})

    stream = await _client(handler).get_livestream("42")
    assert stream is not None


async def test_get_livestream_offline_returns_none():
    client = _client(lambda r: httpx.Response(200, json={"data": []}))
    assert await client.get_livestream("42") is None


async def test_search_categories():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/public/v1/categories"
        assert request.url.params["q"] == "just chatting"
        return httpx.Response(200, json={"data": [{"id": 1, "name": "Just Chatting"}]})

    results = await _client(handler).search_categories("just chatting")
    assert results[0]["name"] == "Just Chatting"


async def test_error_response_raises_kick_api_error():
    client = _client(lambda r: httpx.Response(403, text="forbidden"))
    with pytest.raises(KickAPIError, match="403"):
        await client.get_current_user()
