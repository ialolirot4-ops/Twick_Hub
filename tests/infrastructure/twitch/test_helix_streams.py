from __future__ import annotations

import httpx
import pytest

from twick_hub.domain.enums import Platform
from twick_hub.domain.errors import RateLimitedError
from twick_hub.domain.protocols import BatchLiveStatusProvider
from twick_hub.domain.value_objects import PlatformRef
from twick_hub.infrastructure.twitch.config import WEB_CLIENT_ID
from twick_hub.infrastructure.twitch.helix_streams import (
    MAX_IDS_PER_REQUEST,
    TwitchBatchLiveStatusProvider,
    TwitchHelixError,
    TwitchRateLimitedError,
    map_helix_stream,
)


def _ref(external_id: str) -> PlatformRef:
    return PlatformRef(platform=Platform.TWITCH, external_id=external_id)


def _item(user_id: str, **overrides) -> dict:
    return {
        "id": f"stream-{user_id}",
        "user_id": user_id,
        "user_login": f"user{user_id}",
        "game_name": "Just Chatting",
        "type": "live",
        "title": "hello",
        "viewer_count": 12,
        "started_at": "2026-09-01T10:00:00Z",
        "thumbnail_url": "https://cdn.example/live_user-{width}x{height}.jpg",
        **overrides,
    }


def _provider(handler, clock=lambda: 1000.0) -> TwitchBatchLiveStatusProvider:
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return TwitchBatchLiveStatusProvider(http_client, lambda: "user-token", clock=clock)


def test_satisfies_the_batch_protocol():
    provider = _provider(lambda r: httpx.Response(200, json={"data": []}))
    assert isinstance(provider, BatchLiveStatusProvider)


async def test_sends_repeated_user_id_with_the_expected_headers():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": []})

    await _provider(handler).get_live_streams([_ref("1"), _ref("2")])

    request = seen[0]
    assert request.url.path == "/helix/streams"
    assert request.url.params.get_list("user_id") == ["1", "2"]
    assert request.headers["client-id"] == WEB_CLIENT_ID
    assert request.headers["authorization"] == "Bearer user-token"


async def test_returns_only_live_channels():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [_item("2"), _item("3", type="")]})

    batch = await _provider(handler).get_live_streams([_ref("1"), _ref("2"), _ref("3")])

    assert set(batch.live) == {_ref("2")}  # 1 offline, 3 in an error state
    assert batch.requests_made == 1


async def test_chunks_at_100_ids_per_request():
    sizes = []

    def handler(request: httpx.Request) -> httpx.Response:
        sizes.append(len(request.url.params.get_list("user_id")))
        return httpx.Response(200, json={"data": []})

    refs = [_ref(str(i)) for i in range(1, 251)]
    batch = await _provider(handler).get_live_streams(refs)

    assert MAX_IDS_PER_REQUEST == 100
    assert sizes == [100, 100, 50]
    assert batch.requests_made == 3


async def test_429_reports_seconds_until_ratelimit_reset():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Ratelimit-Reset": "1030"}, text="slow")

    with pytest.raises(TwitchRateLimitedError) as info:
        await _provider(handler, clock=lambda: 1000.0).get_live_streams([_ref("1")])

    assert info.value.retry_after == 30.0
    assert isinstance(info.value, RateLimitedError)


async def test_429_with_a_reset_already_in_the_past_waits_zero_not_negative():
    handler = lambda r: httpx.Response(429, headers={"Ratelimit-Reset": "900"})  # noqa: E731

    with pytest.raises(TwitchRateLimitedError) as info:
        await _provider(handler, clock=lambda: 1000.0).get_live_streams([_ref("1")])

    assert info.value.retry_after == 0.0


async def test_429_without_the_header_reports_none():
    with pytest.raises(TwitchRateLimitedError) as info:
        await _provider(lambda r: httpx.Response(429)).get_live_streams([_ref("1")])

    assert info.value.retry_after is None


async def test_other_errors_raise_helix_error():
    with pytest.raises(TwitchHelixError) as info:
        await _provider(lambda r: httpx.Response(401, text="bad token")).get_live_streams(
            [_ref("1")]
        )

    assert not isinstance(info.value, RateLimitedError)


async def test_a_non_twitch_ref_is_rejected():
    provider = _provider(lambda r: httpx.Response(200, json={"data": []}))

    with pytest.raises(ValueError):
        await provider.get_live_streams([PlatformRef(platform=Platform.KICK, external_id="1")])


def test_map_helix_stream_matches_the_gql_shape_of_the_domain_stream():
    stream = map_helix_stream(_item("42"))

    assert stream.ref == _ref("stream-42")  # the stream's own id, like gql/mappers.map_stream
    assert stream.channel_ref == _ref("42")  # the broadcaster
    assert stream.title == "hello"
    assert stream.category == "Just Chatting"
    assert stream.viewer_count == 12
    assert stream.started_at.year == 2026
    assert stream.thumbnail_url == "https://cdn.example/live_user-440x248.jpg"


def test_map_helix_stream_tolerates_missing_optional_fields():
    stream = map_helix_stream(
        {"id": "s", "user_id": "1", "started_at": "2026-09-01T10:00:00Z", "type": "live"}
    )

    assert stream.title == ""
    assert stream.category is None
    assert stream.thumbnail_url is None
    assert stream.viewer_count == 0
