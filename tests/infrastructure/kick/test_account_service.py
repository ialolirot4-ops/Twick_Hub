from __future__ import annotations

import time

import httpx
import pytest

from twick_hub.domain.protocols import AccountProvider
from twick_hub.infrastructure.kick.account_service import KickAccountService
from twick_hub.infrastructure.kick.client import KickAPIClient
from twick_hub.infrastructure.kick.config import KickAppCredentials
from twick_hub.infrastructure.kick.errors import NotAuthenticatedError
from twick_hub.infrastructure.kick.oauth_flow import KickOAuthFlow
from twick_hub.infrastructure.kick.token_store import KickTokenStore, StoredKickTokens

from .test_oauth_flow import RecordingBrowserOpener, _StateCapturingListener
from .test_token_store import FakeKeyring

_USER_RESPONSE = {"data": [{"user_id": 7, "name": "someone"}]}


def _current_access_token(token_store: KickTokenStore) -> str:
    tokens = token_store.load("user-tokens")
    assert tokens is not None
    return tokens.access_token


def _service(gql_handler, *, connected: bool = False) -> KickAccountService:
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(gql_handler))
    credentials = KickAppCredentials(client_id="c1", client_secret="s1")
    opener = RecordingBrowserOpener()
    listener = _StateCapturingListener(opener, code="auth-code")
    oauth = KickOAuthFlow(credentials, http_client, listener, open_browser=opener)
    token_store = KickTokenStore(FakeKeyring())
    api_client = KickAPIClient(http_client, lambda: _current_access_token(token_store))
    service = KickAccountService(oauth, token_store, api_client)
    if connected:
        token_store.save(
            "user-tokens",
            StoredKickTokens(
                access_token="at1", refresh_token="rt1", expires_at=time.time() + 3600
            ),
        )
    return service


def _combined_handler(oauth_response, api_response):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "id.kick.com":
            return oauth_response(request)
        return api_response(request)

    return handler


def test_satisfies_account_provider_protocol():
    service = _service(lambda r: httpx.Response(200, json=_USER_RESPONSE))
    assert isinstance(service, AccountProvider)


async def test_connect_runs_oauth_then_fetches_the_user():
    def oauth_response(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"access_token": "at1", "refresh_token": "rt1", "expires_in": 3600}
        )

    def api_response(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_USER_RESPONSE)

    service = _service(_combined_handler(oauth_response, api_response))
    account = await service.connect()

    assert account.username == "someone"
    assert account.ref.external_id == "7"


async def test_current_account_returns_none_when_never_connected():
    service = _service(lambda r: httpx.Response(200, json=_USER_RESPONSE))
    assert await service.current_account() is None


async def test_current_account_reflects_a_connected_session():
    service = _service(lambda r: httpx.Response(200, json=_USER_RESPONSE), connected=True)
    account = await service.current_account()
    assert account is not None
    assert account.username == "someone"


async def test_current_account_clears_tokens_that_no_longer_work():
    service = _service(lambda r: httpx.Response(401, text="unauthorized"), connected=True)
    account = await service.current_account()
    assert account is None


async def test_disconnect_revokes_and_deletes():
    revoked = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/revoke":
            revoked.append(request.url.params["token"])
            return httpx.Response(200)
        return httpx.Response(200, json=_USER_RESPONSE)

    service = _service(handler, connected=True)
    await service.disconnect()

    assert revoked == ["at1"]
    assert await service.current_account() is None


async def test_disconnect_without_a_connection_is_a_noop():
    service = _service(lambda r: httpx.Response(200, json=_USER_RESPONSE))
    await service.disconnect()  # must not raise


async def test_ensure_fresh_token_reuses_a_still_valid_token():
    service = _service(lambda r: httpx.Response(200, json=_USER_RESPONSE), connected=True)
    token = await service.ensure_fresh_token()
    assert token == "at1"


async def test_ensure_fresh_token_refreshes_an_expired_one():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "id.kick.com":
            return httpx.Response(
                200, json={"access_token": "at2", "refresh_token": "rt2", "expires_in": 3600}
            )
        return httpx.Response(200, json=_USER_RESPONSE)

    service = _service(handler, connected=True)
    # Force the stored token to look expired.
    service._token_store.save(
        "user-tokens", StoredKickTokens(access_token="at1", refresh_token="rt1", expires_at=0.0)
    )

    token = await service.ensure_fresh_token()

    assert token == "at2"


async def test_ensure_fresh_token_without_a_connection_raises():
    service = _service(lambda r: httpx.Response(200, json=_USER_RESPONSE))
    with pytest.raises(NotAuthenticatedError):
        await service.ensure_fresh_token()
