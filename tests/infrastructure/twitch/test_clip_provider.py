from __future__ import annotations

import httpx
import pytest

from twitchlink_next.domain.enums import Platform
from twitchlink_next.domain.identity import Channel, User
from twitchlink_next.domain.protocols import ClipProvider
from twitchlink_next.domain.value_objects import PlatformRef
from twitchlink_next.infrastructure.twitch.clip_provider import TwitchClipProvider
from twitchlink_next.infrastructure.twitch.gql.client import TwitchGQLClient
from twitchlink_next.infrastructure.twitch.gql.errors import TwitchDataNotFoundError

from .gql.test_client import FakeIntegritySource

_CHANNEL_REF = PlatformRef(platform=Platform.TWITCH, external_id="123")

_CLIP_NODE = {
    "id": "clip1",
    "title": "Clutch moment",
    "game": {"name": "Balatro"},
    "thumbnailURL": "https://example.invalid/clip-thumb.png",
    "slug": "clip1",
    "broadcaster": {"id": "123", "login": "northernlion", "displayName": "NorthernLion"},
    "curator": {"id": "321", "login": "someviewer", "displayName": "SomeViewer"},
    "durationSeconds": 30,
    "createdAt": "2026-09-04T00:00:00Z",
    "viewCount": 500,
}


class FakeChannelDirectory:
    async def find_channel(self, query: str) -> Channel | None:
        raise NotImplementedError

    async def get_channel(self, ref: PlatformRef) -> Channel:
        user = User(ref=ref, username="northernlion", display_name="NorthernLion")
        return Channel(ref=ref, user=user)


def _provider(handler) -> TwitchClipProvider:
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = TwitchGQLClient(http_client, FakeIntegritySource())
    return TwitchClipProvider(client, FakeChannelDirectory())


def test_satisfies_clip_provider_protocol():
    provider = _provider(lambda r: httpx.Response(200, json={"data": {"clip": None}}))
    assert isinstance(provider, ClipProvider)


async def test_get_clip():
    provider = _provider(lambda r: httpx.Response(200, json={"data": {"clip": _CLIP_NODE}}))
    clip = await provider.get_clip(PlatformRef(platform=Platform.TWITCH, external_id="clip1"))
    assert clip.title == "Clutch moment"
    assert clip.creator.username == "someviewer"


async def test_get_clip_raises_when_not_found():
    provider = _provider(lambda r: httpx.Response(200, json={"data": {"clip": None}}))
    with pytest.raises(TwitchDataNotFoundError):
        await provider.get_clip(PlatformRef(platform=Platform.TWITCH, external_id="missing"))


async def test_list_clips_resolves_login_then_lists():
    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        assert "northernlion" in body
        return httpx.Response(
            200,
            json={
                "data": {
                    "user": {
                        "clips": {
                            "edges": [{"cursor": "c1", "node": _CLIP_NODE}],
                            "pageInfo": {"hasNextPage": False},
                        }
                    }
                }
            },
        )

    provider = _provider(handler)
    clips = await provider.list_clips(_CHANNEL_REF)

    assert len(clips) == 1
    assert clips[0].ref.external_id == "clip1"


async def test_list_clips_when_channel_has_none():
    provider = _provider(lambda r: httpx.Response(200, json={"data": {"user": None}}))
    assert await provider.list_clips(_CHANNEL_REF) == []
