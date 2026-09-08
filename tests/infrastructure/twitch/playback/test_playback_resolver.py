from __future__ import annotations

import httpx
import pytest

from twick_hub.domain.enums import MediaKind, Platform
from twick_hub.domain.identity import Channel, User
from twick_hub.domain.protocols import PlaybackResolver
from twick_hub.domain.value_objects import Media, PlatformRef
from twick_hub.infrastructure.twitch.gql.client import TwitchGQLClient
from twick_hub.infrastructure.twitch.playback.errors import (
    ChannelOfflineError,
    GeoBlockedError,
    SubscriberOnlyRestrictedError,
)
from twick_hub.infrastructure.twitch.playback.playback_resolver import (
    NotAuthenticatedError,
    TwitchPlaybackResolver,
    _TwitchPlaybackError,
)

from ..gql.test_client import FakeIntegritySource

_MANIFEST = """
#EXTM3U
#EXT-X-MEDIA:TYPE=VIDEO,GROUP-ID="chunked",NAME="1080p60 (Source)",AUTOSELECT=YES,DEFAULT=YES
1080p60/index-muted.m3u8
#EXT-X-MEDIA:TYPE=VIDEO,GROUP-ID="480p30",NAME="480p30",AUTOSELECT=YES,DEFAULT=YES
480p30/index-muted.m3u8
""".strip()


class FakeChannelDirectory:
    async def find_channel(self, query: str) -> Channel | None:
        raise NotImplementedError

    async def get_channel(self, ref: PlatformRef) -> Channel:
        user = User(ref=ref, username="northernlion", display_name="NorthernLion")
        return Channel(ref=ref, user=user)


def _resolver(gql_handler, manifest_handler, *, token: str | None = "user-token-abc"):
    gql_client = TwitchGQLClient(
        httpx.AsyncClient(transport=httpx.MockTransport(gql_handler)), FakeIntegritySource()
    )
    manifest_http = httpx.AsyncClient(transport=httpx.MockTransport(manifest_handler))
    return TwitchPlaybackResolver(gql_client, manifest_http, FakeChannelDirectory(), lambda: token)


def _stream_media() -> Media:
    ref = PlatformRef(platform=Platform.TWITCH, external_id="123")
    return Media(kind=MediaKind.STREAM, ref=ref, title="Live now", channel_ref=ref)


def _video_media() -> Media:
    ref = PlatformRef(platform=Platform.TWITCH, external_id="999")
    return Media(kind=MediaKind.VIDEO, ref=ref, title="A VOD")


def _clip_media() -> Media:
    ref = PlatformRef(platform=Platform.TWITCH, external_id="clip1")
    return Media(kind=MediaKind.CLIP, ref=ref, title="Clip")


def _token_response(forbidden=False, reason=None, geo_blocked=False) -> dict:
    import json

    value = json.dumps(
        {
            "authorization": {"forbidden": forbidden, "reason": reason},
            "ci_gb": geo_blocked,
            "geoblock_reason": "COPYRIGHT" if geo_blocked else None,
        }
    )
    return {"signature": "sig123", "value": value}


def test_satisfies_playback_resolver_protocol():
    resolver = _resolver(
        lambda r: httpx.Response(200, json={}), lambda r: httpx.Response(200, text="")
    )
    assert isinstance(resolver, PlaybackResolver)


async def test_resolve_requires_authentication():
    resolver = _resolver(
        lambda r: httpx.Response(200, json={}), lambda r: httpx.Response(200, text=""), token=None
    )
    with pytest.raises(NotAuthenticatedError):
        await resolver.resolve(_stream_media(), "best")


async def test_stream_available_qualities_and_resolve_best():
    def gql_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {"data": {"streamPlaybackAccessToken": _token_response()}},
                {"data": {"currentUser": {"hasTurbo": False}}},
            ],
        )

    def manifest_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["sig"] == "sig123"
        return httpx.Response(200, text=_MANIFEST)

    resolver = _resolver(gql_handler, manifest_handler)

    qualities = await resolver.available_qualities(_stream_media())
    assert qualities == ["1080p60", "480p30"]

    source = await resolver.resolve(_stream_media(), "best")
    assert source.quality_label == "1080p60"
    assert source.url.endswith("1080p60/index-muted.m3u8")


async def test_stream_offline_raises():
    def gql_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json=[{"data": {"streamPlaybackAccessToken": None}}, {"data": {}}]
        )

    resolver = _resolver(gql_handler, lambda r: httpx.Response(200, text=""))
    with pytest.raises(ChannelOfflineError):
        await resolver.available_qualities(_stream_media())


async def test_subscriber_only_video_raises_specific_error():
    def gql_handler(request: httpx.Request) -> httpx.Response:
        token = _token_response(forbidden=True, reason="UNAUTHORIZED_ENTITLMENTS")
        return httpx.Response(200, json={"data": {"videoPlaybackAccessToken": token}})

    resolver = _resolver(gql_handler, lambda r: httpx.Response(200, text=_MANIFEST))
    with pytest.raises(SubscriberOnlyRestrictedError):
        await resolver.available_qualities(_video_media())


async def test_geo_blocked_video_raises():
    def gql_handler(request: httpx.Request) -> httpx.Response:
        token = _token_response(geo_blocked=True)
        return httpx.Response(200, json={"data": {"videoPlaybackAccessToken": token}})

    resolver = _resolver(gql_handler, lambda r: httpx.Response(200, text=_MANIFEST))
    with pytest.raises(GeoBlockedError):
        await resolver.available_qualities(_video_media())


async def test_resolve_unavailable_quality_raises():
    def gql_handler(request: httpx.Request) -> httpx.Response:
        token = _token_response()
        return httpx.Response(200, json={"data": {"videoPlaybackAccessToken": token}})

    resolver = _resolver(gql_handler, lambda r: httpx.Response(200, text=_MANIFEST))
    with pytest.raises(_TwitchPlaybackError, match="4k"):
        await resolver.resolve(_video_media(), "4k")


async def test_clip_qualities_come_from_the_token_directly_no_manifest_fetch():
    def gql_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": {
                    "clip": {
                        "playbackAccessToken": {"signature": "clipsig", "value": "clipval"},
                        "videoQualities": [
                            {
                                "quality": "1080",
                                "frameRate": 60,
                                "sourceURL": "https://example.invalid/1080.mp4",
                            },
                            {
                                "quality": "480",
                                "frameRate": 30,
                                "sourceURL": "https://example.invalid/480.mp4",
                            },
                        ],
                    }
                }
            },
        )

    manifest_called = False

    def manifest_handler(request: httpx.Request) -> httpx.Response:
        nonlocal manifest_called
        manifest_called = True
        return httpx.Response(200, text="")

    resolver = _resolver(gql_handler, manifest_handler)
    qualities = await resolver.available_qualities(_clip_media())

    assert qualities == ["1080p60", "480p30"]
    assert manifest_called is False

    source = await resolver.resolve(_clip_media(), "best")
    assert "sig=clipsig" in source.url
    assert "token=clipval" in source.url
