from __future__ import annotations

import httpx
import pytest

from twick_hub.infrastructure.kick.config import KickAppCredentials
from twick_hub.infrastructure.kick.errors import KickAuthError
from twick_hub.infrastructure.kick.oauth_flow import KickOAuthFlow

_CREDENTIALS = KickAppCredentials(client_id="client123", client_secret="secret456")


class FakeRedirectListener:
    def __init__(self, code: str, state_to_return: str) -> None:
        self._code = code
        self._state = state_to_return

    async def wait_for_callback(self, timeout: float) -> tuple[str, str]:
        return self._code, self._state


class RecordingBrowserOpener:
    def __init__(self) -> None:
        self.opened_urls: list[str] = []

    def __call__(self, url: str) -> bool:
        self.opened_urls.append(url)
        return True


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _flow(handler, listener, *, opener=None):
    return KickOAuthFlow(
        _CREDENTIALS, _client(handler), listener, open_browser=opener or RecordingBrowserOpener()
    )


class _StateCapturingListener:
    """Returns whatever state it was actually asked for, by reading it
    back out of the opened authorization URL — used to test the happy
    path without hardcoding a state value the flow itself generates."""

    def __init__(self, opener: RecordingBrowserOpener, code: str) -> None:
        self._opener = opener
        self._code = code

    async def wait_for_callback(self, timeout: float) -> tuple[str, str]:
        from urllib.parse import parse_qs, urlparse

        url = self._opener.opened_urls[-1]
        state = parse_qs(urlparse(url).query)["state"][0]
        return self._code, state


async def test_authorize_opens_the_correct_url_and_exchanges_the_code():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/oauth/token"
        body = request.content.decode()
        assert "grant_type=authorization_code" in body
        assert "code=auth-code-1" in body
        assert "client_secret=secret456" in body
        return httpx.Response(
            200, json={"access_token": "at1", "refresh_token": "rt1", "expires_in": 3600}
        )

    opener = RecordingBrowserOpener()
    listener = _StateCapturingListener(opener, code="auth-code-1")
    flow = _flow(handler, listener, opener=opener)

    tokens = await flow.authorize()

    assert tokens.access_token == "at1"
    assert tokens.refresh_token == "rt1"
    assert opener.opened_urls[0].startswith("https://id.kick.com/oauth/authorize?")
    assert "code_challenge=" in opener.opened_urls[0]
    assert "code_challenge_method=S256" in opener.opened_urls[0]


async def test_authorize_rejects_a_mismatched_state():
    flow = _flow(
        lambda r: httpx.Response(200, json={}), FakeRedirectListener("code1", "wrong-state")
    )
    with pytest.raises(KickAuthError, match="state"):
        await flow.authorize()


async def test_authorize_without_credentials_raises():
    no_creds = KickAppCredentials(client_id=None, client_secret=None)
    flow = KickOAuthFlow(
        no_creds,
        _client(lambda r: httpx.Response(200)),
        FakeRedirectListener("c", "s"),
        open_browser=RecordingBrowserOpener(),
    )
    with pytest.raises(KickAuthError, match="configured"):
        await flow.authorize()


async def test_exchange_failure_raises_with_response_body():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="invalid_grant")

    opener = RecordingBrowserOpener()
    listener = _StateCapturingListener(opener, code="bad-code")
    flow = _flow(handler, listener, opener=opener)

    with pytest.raises(KickAuthError, match="invalid_grant"):
        await flow.authorize()


async def test_refresh_returns_new_tokens():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "grant_type=refresh_token" in request.content.decode()
        assert "refresh_token=old-refresh" in request.content.decode()
        return httpx.Response(
            200, json={"access_token": "at2", "refresh_token": "rt2", "expires_in": 3600}
        )

    flow = _flow(handler, FakeRedirectListener("", ""))
    tokens = await flow.refresh("old-refresh")

    assert tokens.access_token == "at2"


async def test_revoke_sends_token_as_query_param():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["token"] == "at1"
        assert request.url.params["token_hint_type"] == "access_token"
        return httpx.Response(200)

    flow = _flow(handler, FakeRedirectListener("", ""))
    await flow.revoke("at1")  # must not raise


async def test_revoke_failure_raises():
    flow = _flow(lambda r: httpx.Response(400, text="bad token"), FakeRedirectListener("", ""))
    with pytest.raises(KickAuthError):
        await flow.revoke("at1")


async def test_introspect_active_token():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer at1"
        return httpx.Response(200, json={"data": {"active": True, "scope": "user:read"}})

    flow = _flow(handler, FakeRedirectListener("", ""))
    result = await flow.introspect("at1")

    assert result.active is True
    assert result.scope == "user:read"


async def test_introspect_inactive_or_error_response_reports_inactive():
    flow = _flow(lambda r: httpx.Response(401), FakeRedirectListener("", ""))
    result = await flow.introspect("expired-token")
    assert result.active is False
