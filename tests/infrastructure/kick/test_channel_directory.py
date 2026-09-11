from __future__ import annotations

import httpx
import pytest

from twick_hub.domain.enums import Platform
from twick_hub.domain.protocols import ChannelDirectory, LiveStreamProvider
from twick_hub.domain.value_objects import PlatformRef
from twick_hub.infrastructure.kick.channel_directory import KickChannelDirectory
from twick_hub.infrastructure.kick.client import KickAPIClient
from twick_hub.infrastructure.kick.errors import KickDataNotFoundError

_CHANNEL = {"broadcaster_user_id": 123456, "slug": "xqc", "stream_title": "Live", "stream": None}


def _directory(handler) -> KickChannelDirectory:
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return KickChannelDirectory(KickAPIClient(http_client, lambda: "token"))


def test_satisfies_channel_directory_and_live_stream_provider_protocols():
    directory = _directory(lambda r: httpx.Response(200, json={"data": []}))
    assert isinstance(directory, ChannelDirectory)
    assert isinstance(directory, LiveStreamProvider)


async def test_find_channel_by_bare_slug():
    directory = _directory(lambda r: httpx.Response(200, json={"data": [_CHANNEL]}))
    channel = await directory.find_channel("xqc")
    assert channel is not None
    assert channel.user.username == "xqc"


async def test_find_channel_by_full_url():
    directory = _directory(lambda r: httpx.Response(200, json={"data": [_CHANNEL]}))
    channel = await directory.find_channel("https://kick.com/xqc")
    assert channel is not None


async def test_find_channel_with_unparseable_query_returns_none_without_a_request():
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={"data": []})

    result = await _directory(handler).find_channel("not a valid channel!!")
    assert result is None
    assert called is False


async def test_find_channel_not_found_returns_none():
    directory = _directory(lambda r: httpx.Response(200, json={"data": []}))
    assert await directory.find_channel("doesnotexist") is None


async def test_get_channel_raises_when_not_found():
    directory = _directory(lambda r: httpx.Response(200, json={"data": []}))
    with pytest.raises(KickDataNotFoundError):
        await directory.get_channel(PlatformRef(platform=Platform.KICK, external_id="999"))


async def test_get_live_stream_when_offline():
    directory = _directory(lambda r: httpx.Response(200, json={"data": []}))
    ref = PlatformRef(platform=Platform.KICK, external_id="123456")
    stream = await directory.get_live_stream(ref)
    assert stream is None


async def test_get_live_stream_when_live():
    live_data = {
        "broadcaster_user_id": 123456,
        "stream_title": "Ranked",
        "viewer_count": 10,
        "started_at": "2026-09-05T10:00:00+00:00",
    }
    directory = _directory(lambda r: httpx.Response(200, json={"data": [live_data]}))
    ref = PlatformRef(platform=Platform.KICK, external_id="123456")
    stream = await directory.get_live_stream(ref)
    assert stream is not None
    assert stream.viewer_count == 10
