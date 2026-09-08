from __future__ import annotations

import httpx
import pytest

from twick_hub.domain.enums import Platform
from twick_hub.domain.protocols import ChannelDirectory, LiveStreamProvider
from twick_hub.domain.value_objects import PlatformRef
from twick_hub.infrastructure.twitch.channel_directory import TwitchChannelDirectory
from twick_hub.infrastructure.twitch.gql.client import TwitchGQLClient
from twick_hub.infrastructure.twitch.gql.errors import TwitchDataNotFoundError

from .gql.test_client import FakeIntegritySource

_CHANNEL_USER = {
    "id": "123",
    "login": "northernlion",
    "displayName": "NorthernLion",
    "roles": {"isPartner": True, "isAffiliate": False},
    "followers": {"totalCount": 900000},
    "stream": None,
}


def _directory(handler) -> TwitchChannelDirectory:
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return TwitchChannelDirectory(TwitchGQLClient(http_client, FakeIntegritySource()))


def test_satisfies_channel_directory_and_live_stream_provider_protocols():
    directory = _directory(lambda r: httpx.Response(200, json={"data": {"user": None}}))
    assert isinstance(directory, ChannelDirectory)
    assert isinstance(directory, LiveStreamProvider)


async def test_find_channel_by_bare_login():
    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        assert "northernlion" in body
        return httpx.Response(200, json={"data": {"user": _CHANNEL_USER}})

    channel = await _directory(handler).find_channel("northernlion")

    assert channel is not None
    assert channel.user.username == "northernlion"


async def test_find_channel_by_full_url():
    directory = _directory(lambda r: httpx.Response(200, json={"data": {"user": _CHANNEL_USER}}))
    channel = await directory.find_channel("https://www.twitch.tv/northernlion?something=1")
    assert channel is not None


async def test_find_channel_with_an_unparseable_query_returns_none_without_a_request():
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={"data": {"user": None}})

    result = await _directory(handler).find_channel("not a valid channel or url!!")

    assert result is None
    assert called is False


async def test_find_channel_not_found_returns_none():
    directory = _directory(lambda r: httpx.Response(200, json={"data": {"user": None}}))
    assert await directory.find_channel("doesnotexist") is None


async def test_find_channel_with_id_zero_placeholder_returns_none():
    directory = _directory(
        lambda r: httpx.Response(200, json={"data": {"user": {"id": "0", "login": ""}}})
    )
    assert await directory.find_channel("deleteduser") is None


async def test_get_channel_raises_when_not_found():
    directory = _directory(lambda r: httpx.Response(200, json={"data": {"user": None}}))
    with pytest.raises(TwitchDataNotFoundError):
        await directory.get_channel(PlatformRef(platform=Platform.TWITCH, external_id="999"))


async def test_get_live_stream_when_offline():
    directory = _directory(lambda r: httpx.Response(200, json={"data": {"user": _CHANNEL_USER}}))
    ref = PlatformRef(platform=Platform.TWITCH, external_id="123")
    stream = await directory.get_live_stream(ref)
    assert stream is None


async def test_get_live_stream_when_live():
    live_user = {
        **_CHANNEL_USER,
        "stream": {
            "id": "555",
            "title": "Ranked run",
            "game": {"name": "Balatro"},
            "previewImageURL": "https://example.invalid/p.png",
            "createdAt": "2026-09-05T00:00:00Z",
            "viewersCount": 42,
        },
    }
    directory = _directory(lambda r: httpx.Response(200, json={"data": {"user": live_user}}))
    ref = PlatformRef(platform=Platform.TWITCH, external_id="123")
    stream = await directory.get_live_stream(ref)

    assert stream is not None
    assert stream.viewer_count == 42
