from __future__ import annotations

import httpx
import pytest

from twick_hub.domain.enums import Platform
from twick_hub.domain.protocols import BatchLiveStatusProvider
from twick_hub.domain.value_objects import PlatformRef
from twick_hub.infrastructure.kick.client import KickAPIClient
from twick_hub.infrastructure.kick.errors import KickAPIError
from twick_hub.infrastructure.kick.livestream_batch import (
    MAX_IDS_PER_REQUEST,
    KickBatchLiveStatusProvider,
)


def _ref(external_id: str) -> PlatformRef:
    return PlatformRef(platform=Platform.KICK, external_id=external_id)


def _item(broadcaster_id: int, **overrides) -> dict:
    return {
        "broadcaster_user_id": broadcaster_id,
        "slug": f"chan{broadcaster_id}",
        "stream_title": "hello",
        "viewer_count": 7,
        "started_at": "2026-09-01T10:00:00Z",
        "category": {"id": 1, "name": "Just Chatting"},
        **overrides,
    }


def _provider(handler) -> KickBatchLiveStatusProvider:
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return KickBatchLiveStatusProvider(KickAPIClient(http_client, lambda: "token"))


def test_satisfies_the_batch_protocol():
    assert isinstance(
        _provider(lambda r: httpx.Response(200, json={"data": []})), BatchLiveStatusProvider
    )


async def test_returns_only_live_channels_keyed_by_ref():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [_item(2)]})

    batch = await _provider(handler).get_live_streams([_ref("1"), _ref("2")])

    assert set(batch.live) == {_ref("2")}  # "1" is absent → offline
    assert batch.live[_ref("2")].title == "hello"
    assert batch.live[_ref("2")].category == "Just Chatting"
    assert batch.requests_made == 1


async def test_chunks_at_the_documented_50_ids_per_request():
    seen_chunks: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_chunks.append(request.url.params.get_list("broadcaster_user_id"))
        return httpx.Response(200, json={"data": []})

    refs = [_ref(str(i)) for i in range(1, 121)]  # 120 channels
    batch = await _provider(handler).get_live_streams(refs)

    assert MAX_IDS_PER_REQUEST == 50
    assert [len(chunk) for chunk in seen_chunks] == [50, 50, 20]
    assert batch.requests_made == 3
    assert [i for chunk in seen_chunks for i in chunk] == [str(i) for i in range(1, 121)]


async def test_duplicate_refs_are_asked_about_once():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params.get_list("broadcaster_user_id"))
        return httpx.Response(200, json={"data": []})

    await _provider(handler).get_live_streams([_ref("1"), _ref("1")])

    assert seen == [["1"]]


async def test_no_channels_makes_no_request():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected")

    batch = await _provider(handler).get_live_streams([])

    assert batch.live == {}
    assert batch.requests_made == 0


async def test_a_response_item_that_was_not_asked_for_is_ignored():
    handler = lambda r: httpx.Response(200, json={"data": [_item(1), _item(99)]})  # noqa: E731

    batch = await _provider(handler).get_live_streams([_ref("1")])

    assert set(batch.live) == {_ref("1")}


async def test_a_non_kick_ref_is_rejected():
    provider = _provider(lambda r: httpx.Response(200, json={"data": []}))

    with pytest.raises(ValueError):
        await provider.get_live_streams([PlatformRef(platform=Platform.TWITCH, external_id="1")])


async def test_an_unparseable_item_fails_the_whole_batch_instead_of_reading_as_offline():
    bad = _item(1)
    del bad["started_at"]
    provider = _provider(lambda r: httpx.Response(200, json={"data": [bad, _item(2)]}))

    with pytest.raises(KickAPIError):
        await provider.get_live_streams([_ref("1"), _ref("2")])


async def test_an_error_on_a_later_chunk_discards_the_earlier_chunk():
    calls = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        calls[0] += 1
        if calls[0] == 2:
            return httpx.Response(500, text="boom")
        return httpx.Response(200, json={"data": [_item(1)]})

    refs = [_ref(str(i)) for i in range(1, 61)]
    with pytest.raises(KickAPIError):
        await _provider(handler).get_live_streams(refs)  # partial data is never returned
