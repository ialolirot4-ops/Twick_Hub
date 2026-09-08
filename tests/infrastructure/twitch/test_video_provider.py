from __future__ import annotations

import httpx
import pytest

from twick_hub.domain.enums import Platform
from twick_hub.domain.identity import Channel, User
from twick_hub.domain.protocols import VideoProvider
from twick_hub.domain.value_objects import PlatformRef
from twick_hub.infrastructure.twitch.gql.client import TwitchGQLClient
from twick_hub.infrastructure.twitch.gql.errors import TwitchDataNotFoundError
from twick_hub.infrastructure.twitch.video_provider import TwitchVideoProvider

from .gql.test_client import FakeIntegritySource

_CHANNEL_REF = PlatformRef(platform=Platform.TWITCH, external_id="123")

_VIDEO_NODE = {
    "id": "999",
    "title": "Full playthrough",
    "game": {"name": "Balatro"},
    "previewThumbnailURL": "https://example.invalid/thumb.png",
    "owner": {"id": "123", "login": "northernlion", "displayName": "NorthernLion"},
    "lengthSeconds": 7200,
    "createdAt": "2026-09-01T00:00:00Z",
    "publishedAt": "2026-09-01T01:00:00Z",
    "viewCount": 15000,
}


class FakeChannelDirectory:
    async def find_channel(self, query: str) -> Channel | None:
        raise NotImplementedError

    async def get_channel(self, ref: PlatformRef) -> Channel:
        user = User(ref=ref, username="northernlion", display_name="NorthernLion")
        return Channel(ref=ref, user=user)


def _provider(handler) -> TwitchVideoProvider:
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = TwitchGQLClient(http_client, FakeIntegritySource())
    return TwitchVideoProvider(client, FakeChannelDirectory())


def test_satisfies_video_provider_protocol():
    provider = _provider(lambda r: httpx.Response(200, json={"data": {"video": None}}))
    assert isinstance(provider, VideoProvider)


async def test_get_video():
    provider = _provider(lambda r: httpx.Response(200, json={"data": {"video": _VIDEO_NODE}}))
    video = await provider.get_video(PlatformRef(platform=Platform.TWITCH, external_id="999"))
    assert video.title == "Full playthrough"
    assert video.duration.total_seconds == 7200


async def test_get_video_raises_when_not_found():
    provider = _provider(lambda r: httpx.Response(200, json={"data": {"video": None}}))
    with pytest.raises(TwitchDataNotFoundError):
        await provider.get_video(PlatformRef(platform=Platform.TWITCH, external_id="000"))


async def test_list_videos_resolves_login_then_lists():
    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        assert "northernlion" in body
        return httpx.Response(
            200,
            json={
                "data": {
                    "user": {
                        "videos": {
                            "edges": [{"cursor": "c1", "node": _VIDEO_NODE}],
                            "pageInfo": {"hasNextPage": False},
                        }
                    }
                }
            },
        )

    provider = _provider(handler)
    videos = await provider.list_videos(_CHANNEL_REF)

    assert len(videos) == 1
    assert videos[0].ref.external_id == "999"


async def test_list_videos_when_channel_has_none():
    provider = _provider(lambda r: httpx.Response(200, json={"data": {"user": None}}))
    assert await provider.list_videos(_CHANNEL_REF) == []
