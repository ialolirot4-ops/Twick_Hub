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


# FASE 18 — Testing: the cases above only exercise the "happy path" plus a
# handful of error branches; the ones below close the remaining gaps found
# by measuring coverage against the real test suite (docs/phase-state.md).


async def test_unsupported_media_kind_raises_value_error():
    """``MediaKind`` only has three real members (stream/video/clip) today,
    so this defensive branch can't be reached through any value the enum
    actually produces — but ``Media`` is a plain, unvalidated dataclass, so
    a caller (or a future ``MediaKind`` member no adapter has been updated
    for yet) really can hand the resolver something else. Confirms the
    exhaustiveness guard itself, not a reachable-today user scenario.
    """
    ref = PlatformRef(platform=Platform.TWITCH, external_id="1")
    bogus_media = Media(kind="unknown", ref=ref, title="x")  # type: ignore[arg-type]
    resolver = _resolver(
        lambda r: httpx.Response(200, json={}), lambda r: httpx.Response(200, text="")
    )
    with pytest.raises(ValueError, match="Unsupported media kind"):
        await resolver.available_qualities(bogus_media)


async def test_video_offline_raises():
    def gql_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"videoPlaybackAccessToken": None}})

    resolver = _resolver(gql_handler, lambda r: httpx.Response(200, text=""))
    with pytest.raises(ChannelOfflineError):
        await resolver.available_qualities(_video_media())


async def test_video_forbidden_with_generic_reason_raises_playback_forbidden():
    from twick_hub.infrastructure.twitch.playback.errors import PlaybackForbiddenError

    def gql_handler(request: httpx.Request) -> httpx.Response:
        token = _token_response(forbidden=True, reason="SOME_OTHER_REASON")
        return httpx.Response(200, json={"data": {"videoPlaybackAccessToken": token}})

    resolver = _resolver(gql_handler, lambda r: httpx.Response(200, text=_MANIFEST))
    with pytest.raises(PlaybackForbiddenError, match="SOME_OTHER_REASON"):
        await resolver.available_qualities(_video_media())


async def test_clip_not_found_returns_no_variants_and_resolve_raises():
    """``clip_data is None`` (line ``_clip_variants``'s ``return []``) and
    ``_select_quality``'s own "no variants" guard are two different lines —
    this single scenario is the only way to reach both together, since
    every other path that could produce an empty variant list raises its
    own, more specific ``offline_error`` first (``_fetch_manifest``)."""

    def gql_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"clip": None}})

    resolver = _resolver(gql_handler, lambda r: httpx.Response(200, text=""))

    assert await resolver.available_qualities(_clip_media()) == []
    with pytest.raises(_TwitchPlaybackError, match="No playable quality variants"):
        await resolver.resolve(_clip_media(), "best")


async def test_manifest_404_raises_offline_error():
    def gql_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {"data": {"streamPlaybackAccessToken": _token_response()}},
                {"data": {"currentUser": {"hasTurbo": False}}},
            ],
        )

    resolver = _resolver(gql_handler, lambda r: httpx.Response(404))
    with pytest.raises(ChannelOfflineError):
        await resolver.available_qualities(_stream_media())


async def test_manifest_with_no_recognizable_variants_raises_offline_error():
    def gql_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {"data": {"streamPlaybackAccessToken": _token_response()}},
                {"data": {"currentUser": {"hasTurbo": False}}},
            ],
        )

    resolver = _resolver(gql_handler, lambda r: httpx.Response(200, text="#EXTM3U\n"))
    with pytest.raises(ChannelOfflineError):
        await resolver.available_qualities(_stream_media())


async def test_resolve_by_exact_quality_name_returns_matching_variant():
    """Distinct from ``resolve(..., \"best\")`` (short-circuits to the first
    variant) and from the not-found case (falls through the whole loop) —
    this is the loop actually finding its match on a middle/last variant."""

    def gql_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {"data": {"streamPlaybackAccessToken": _token_response()}},
                {"data": {"currentUser": {"hasTurbo": False}}},
            ],
        )

    resolver = _resolver(gql_handler, lambda r: httpx.Response(200, text=_MANIFEST))
    source = await resolver.resolve(_stream_media(), "480p30")
    assert source.quality_label == "480p30"
