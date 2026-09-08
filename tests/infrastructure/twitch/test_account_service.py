from __future__ import annotations

import httpx
import pytest

from tests.infrastructure.twitch.test_token_store import FakeKeyring
from twick_hub.domain.protocols import AccountProvider
from twick_hub.infrastructure.twitch.account_service import TwitchAccountService
from twick_hub.infrastructure.twitch.browser_cookie_import import BrowserProfile
from twick_hub.infrastructure.twitch.errors import NoBrowserSessionFoundError
from twick_hub.infrastructure.twitch.token_store import TwitchTokenStore


class FakeCookieImporter:
    def __init__(self, profiles=None, token: str = "session-token-abc") -> None:
        default_profiles = [BrowserProfile(key="p", display_name="default")]
        self._profiles = profiles if profiles is not None else default_profiles
        self._token = token

    def list_profiles(self) -> list[BrowserProfile]:
        return self._profiles

    def import_session_token(self, profile: BrowserProfile) -> str:
        return self._token


def _validate_handler(request: httpx.Request) -> httpx.Response:
    token = request.headers.get("authorization", "")
    if token != "OAuth session-token-abc":
        return httpx.Response(401, json={"status": 401, "message": "invalid token"})
    return httpx.Response(
        200,
        json={"client_id": "x", "login": "northernlion", "user_id": "123", "expires_in": 3600},
    )


def test_account_service_satisfies_the_account_provider_protocol():
    service = TwitchAccountService(
        FakeCookieImporter(), TwitchTokenStore(FakeKeyring()), httpx.AsyncClient()
    )
    assert isinstance(service, AccountProvider)


async def test_connect_imports_validates_and_stores_the_token():
    token_store = TwitchTokenStore(FakeKeyring())
    client = httpx.AsyncClient(transport=httpx.MockTransport(_validate_handler))
    service = TwitchAccountService(FakeCookieImporter(), token_store, client)

    account = await service.connect()

    assert account.username == "northernlion"
    assert account.ref.external_id == "123"
    assert token_store.load("user-session-token") == "session-token-abc"


async def test_connect_with_no_browser_profiles_raises():
    service = TwitchAccountService(
        FakeCookieImporter(profiles=[]),
        TwitchTokenStore(FakeKeyring()),
        httpx.AsyncClient(transport=httpx.MockTransport(_validate_handler)),
    )
    with pytest.raises(NoBrowserSessionFoundError):
        await service.connect()


async def test_current_account_returns_none_when_never_connected():
    client = httpx.AsyncClient(transport=httpx.MockTransport(_validate_handler))
    service = TwitchAccountService(FakeCookieImporter(), TwitchTokenStore(FakeKeyring()), client)
    assert await service.current_account() is None


async def test_current_account_reflects_a_stored_token():
    token_store = TwitchTokenStore(FakeKeyring())
    client = httpx.AsyncClient(transport=httpx.MockTransport(_validate_handler))
    service = TwitchAccountService(FakeCookieImporter(), token_store, client)
    await service.connect()

    account = await service.current_account()

    assert account is not None
    assert account.username == "northernlion"


async def test_current_account_clears_an_expired_token():
    token_store = TwitchTokenStore(FakeKeyring())
    token_store.save("user-session-token", "a-token-twitch-will-reject")
    client = httpx.AsyncClient(transport=httpx.MockTransport(_validate_handler))
    service = TwitchAccountService(FakeCookieImporter(), token_store, client)

    account = await service.current_account()

    assert account is None
    assert token_store.load("user-session-token") is None


async def test_disconnect_revokes_and_deletes_the_token():
    revoke_called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal revoke_called
        if request.url.path == "/oauth2/revoke":
            revoke_called = True
            return httpx.Response(200)
        return _validate_handler(request)

    token_store = TwitchTokenStore(FakeKeyring())
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = TwitchAccountService(FakeCookieImporter(), token_store, client)
    await service.connect()

    await service.disconnect()

    assert revoke_called is True
    assert token_store.load("user-session-token") is None


async def test_disconnect_without_a_stored_token_is_a_noop():
    service = TwitchAccountService(
        FakeCookieImporter(),
        TwitchTokenStore(FakeKeyring()),
        httpx.AsyncClient(transport=httpx.MockTransport(_validate_handler)),
    )
    await service.disconnect()  # must not raise
