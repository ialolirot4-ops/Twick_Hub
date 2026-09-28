"""FASE 21c — ``bootstrap/platforms.py``: the real Twitch/Kick adapters
composed the way ``main()`` composes them, driven through
``httpx.MockTransport`` so nothing touches the network.

What this cannot show (needs a real machine, see
scripts/verify_21c_live.py): that Twitch/Kick actually accept these
requests, the Firefox cookie import, the Integrity capture, and the Kick
OAuth token exchange.
"""

from __future__ import annotations

import logging
import time

import httpx
from pydantic import SecretStr
from PySide6.QtNetwork import QNetworkAccessManager

from twick_hub.bootstrap import platforms
from twick_hub.bootstrap.platforms import build_platform_adapters
from twick_hub.config.settings import AppConfig
from twick_hub.domain.enums import Platform
from twick_hub.infrastructure.kick.token_store import KickTokenStore, StoredKickTokens
from twick_hub.infrastructure.twitch.config import WEB_CLIENT_ID
from twick_hub.infrastructure.twitch.token_store import TwitchTokenStore

_SECRET = "kick-secret-that-must-not-leak"

_TWITCH_USER = {
    "id": "123",
    "login": "northernlion",
    "displayName": "NorthernLion",
    "roles": {"isPartner": True, "isAffiliate": False},
    "followers": {"totalCount": 900000},
    "stream": None,
}
_KICK_CHANNEL = {
    "broadcaster_user_id": 123456,
    "slug": "xqc",
    "stream_title": "Live",
    "stream": None,
}


class _FakeKeyring:
    def __init__(self, *, broken: bool = False) -> None:
        self._data: dict[tuple[str, str], str] = {}
        self._broken = broken

    def set_password(self, service_name: str, username: str, password: str) -> None:
        if self._broken:
            raise RuntimeError("no backend")
        self._data[(service_name, username)] = password

    def get_password(self, service_name: str, username: str) -> str | None:
        if self._broken:
            raise RuntimeError("no backend")
        return self._data.get((service_name, username))

    def delete_password(self, service_name: str, username: str) -> None:
        self._data.pop((service_name, username), None)


def _config(tmp_path, *, kick: bool) -> AppConfig:
    if not kick:
        return AppConfig(data_dir=tmp_path)
    return AppConfig(
        data_dir=tmp_path, kick_client_id="kick-cid", kick_client_secret=SecretStr(_SECRET)
    )


def _build(config: AppConfig, handler=None) -> dict:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler)) if handler else None
    return build_platform_adapters(
        config, network_manager=QNetworkAccessManager(), http_client=client
    )


def test_twitch_gets_every_adapter_but_live_monitor(qapp, tmp_path):
    adapters = _build(_config(tmp_path, kick=False))[Platform.TWITCH]

    assert adapters.account is not None
    assert adapters.channel_directory is not None
    assert adapters.live_stream_provider is not None
    assert adapters.video_provider is not None
    assert adapters.clip_provider is not None
    assert adapters.playback_resolver is not None
    assert adapters.live_monitor is None  # 21d: needs the Twitch app credentials


def test_kick_stays_empty_without_app_credentials(qapp, tmp_path):
    adapters = _build(_config(tmp_path, kick=False))[Platform.KICK]

    assert adapters.account is None
    assert adapters.channel_directory is None
    assert adapters.live_stream_provider is None


def test_kick_gets_account_and_search_but_no_media_when_configured(qapp, tmp_path):
    adapters = _build(_config(tmp_path, kick=True))[Platform.KICK]

    assert adapters.account is not None
    assert adapters.channel_directory is not None
    assert adapters.live_stream_provider is not None
    assert adapters.video_provider is None  # no official VOD API (docs/kick-audit.md)
    assert adapters.clip_provider is None
    assert adapters.playback_resolver is None


def test_kick_secret_is_never_logged(qapp, tmp_path, caplog):
    with caplog.at_level(logging.DEBUG):
        _build(_config(tmp_path, kick=True))
        _build(_config(tmp_path, kick=False))

    assert _SECRET not in caplog.text


async def test_twitch_lookup_goes_through_the_real_gql_client(qapp, tmp_path):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": {"user": _TWITCH_USER}})

    directory = _build(_config(tmp_path, kick=False), handler)[Platform.TWITCH].channel_directory
    assert directory is not None

    channel = await directory.find_channel("northernlion")

    assert channel is not None
    assert channel.user.username == "northernlion"
    assert seen[0].url.host == "gql.twitch.tv"
    assert seen[0].headers["client-id"] == WEB_CLIENT_ID


async def test_kick_lookup_sends_the_stored_access_token(qapp, tmp_path, monkeypatch):
    store = KickTokenStore(_FakeKeyring())
    store.save(
        "user-tokens",
        StoredKickTokens(access_token="at1", refresh_token="rt1", expires_at=time.time() + 3600),
    )
    monkeypatch.setattr(platforms, "KickTokenStore", lambda: store)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": [_KICK_CHANNEL]})

    directory = _build(_config(tmp_path, kick=True), handler)[Platform.KICK].channel_directory
    assert directory is not None

    channel = await directory.find_channel("xqc")

    assert channel is not None
    assert seen[0].headers["authorization"] == "Bearer at1"


def test_unusable_credential_store_reads_as_no_twitch_session(caplog):
    get_user_token = platforms._twitch_user_token_getter(
        TwitchTokenStore(_FakeKeyring(broken=True))
    )

    with caplog.at_level(logging.WARNING):
        assert get_user_token() is None

    assert "credential store unavailable" in caplog.text
