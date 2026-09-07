from __future__ import annotations

import httpx
import pytest

from twitchlink_next.infrastructure.twitch.app_token_provider import AppTokenProvider
from twitchlink_next.infrastructure.twitch.config import TwitchAppCredentials
from twitchlink_next.infrastructure.twitch.errors import (
    TokenRefreshFailedError,
    TokenRevokeFailedError,
)

_CREDENTIALS = TwitchAppCredentials(client_id="client123", client_secret="secret456")


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_get_token_fetches_from_the_token_endpoint():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/oauth2/token"
        return httpx.Response(200, json={"access_token": "app-token-1", "expires_in": 3600})

    provider = AppTokenProvider(_CREDENTIALS, _client(handler))
    token = await provider.get_token()

    assert token.value == "app-token-1"
    assert token.is_valid()


async def test_get_token_reuses_the_cached_token_before_expiry():
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200, json={"access_token": f"app-token-{call_count}", "expires_in": 3600}
        )

    provider = AppTokenProvider(_CREDENTIALS, _client(handler))
    first = await provider.get_token()
    second = await provider.get_token()

    assert first.value == second.value
    assert call_count == 1


async def test_get_token_refetches_once_the_cached_token_expires():
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        # Shorter than the provider's safety margin, so it's already
        # treated as expired on the very next call.
        payload = {"access_token": f"app-token-{call_count}", "expires_in": 1}
        return httpx.Response(200, json=payload)

    provider = AppTokenProvider(_CREDENTIALS, _client(handler))
    first = await provider.get_token()
    second = await provider.get_token()

    assert first.value != second.value
    assert call_count == 2


async def test_get_token_without_credentials_raises():
    no_creds = TwitchAppCredentials(client_id=None, client_secret=None)
    provider = AppTokenProvider(no_creds, _client(lambda r: httpx.Response(200)))
    with pytest.raises(TokenRefreshFailedError, match="configured"):
        await provider.get_token()


async def test_get_token_http_error_raises_refresh_failed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"message": "invalid client"})

    provider = AppTokenProvider(_CREDENTIALS, _client(handler))
    with pytest.raises(TokenRefreshFailedError):
        await provider.get_token()


async def test_revoke_clears_the_cache():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            return httpx.Response(200, json={"access_token": "app-token-1", "expires_in": 3600})
        assert request.url.path == "/oauth2/revoke"
        return httpx.Response(200)

    provider = AppTokenProvider(_CREDENTIALS, _client(handler))
    await provider.get_token()
    await provider.revoke()

    # No cached token left, and no credentials issue either — the next
    # get_token() would hit the network again (proven by test above), not
    # return a stale value.
    assert provider._cached is None


async def test_revoke_without_a_cached_token_is_a_noop():
    provider = AppTokenProvider(_CREDENTIALS, _client(lambda r: httpx.Response(200)))
    await provider.revoke()  # must not raise, must not make any request


async def test_revoke_http_error_still_clears_cache_and_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            return httpx.Response(200, json={"access_token": "app-token-1", "expires_in": 3600})
        return httpx.Response(500)

    provider = AppTokenProvider(_CREDENTIALS, _client(handler))
    await provider.get_token()

    with pytest.raises(TokenRevokeFailedError):
        await provider.revoke()

    assert provider._cached is None
