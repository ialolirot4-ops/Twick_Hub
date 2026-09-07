from __future__ import annotations

import httpx
import pytest

from twitchlink_next.infrastructure.twitch.gql.client import TwitchGQLClient
from twitchlink_next.infrastructure.twitch.gql.errors import (
    TwitchGQLRequestError,
    TwitchIntegrityCheckFailedError,
)
from twitchlink_next.infrastructure.twitch.gql.operations import GET_CHANNEL, GET_CHANNEL_VIDEOS


class FakeIntegritySource:
    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self.headers = headers or {"Client-Integrity": "fake-integrity-value"}
        self.call_count = 0

    async def get_headers(self) -> dict[str, str]:
        self.call_count += 1
        return self.headers


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_send_includes_client_id_header():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["client-id"] == "kimne78kx3ncx6brgo4mv6wki5h1ko"
        return httpx.Response(200, json={"data": {}})

    client = TwitchGQLClient(_client(handler), FakeIntegritySource())
    await client.send(GET_CHANNEL, {"login": "northernlion"})


async def test_send_does_not_request_integrity_for_metadata_only_operations():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "client-integrity" not in request.headers
        return httpx.Response(200, json={"data": {}})

    integrity = FakeIntegritySource()
    client = TwitchGQLClient(_client(handler), integrity)
    await client.send(GET_CHANNEL, {"login": "northernlion"})

    assert integrity.call_count == 0


async def test_send_requests_integrity_for_channel_videos():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["client-integrity"] == "fake-integrity-value"
        return httpx.Response(200, json={"data": {}})

    integrity = FakeIntegritySource()
    client = TwitchGQLClient(_client(handler), integrity)
    await client.send(GET_CHANNEL_VIDEOS, {"login": "northernlion"})

    assert integrity.call_count == 1


async def test_send_raises_on_failed_integrity_check():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"errors": [{"message": "failed integrity check"}]})

    client = TwitchGQLClient(_client(handler), FakeIntegritySource())
    with pytest.raises(TwitchIntegrityCheckFailedError):
        await client.send(GET_CHANNEL_VIDEOS, {"login": "x"})


async def test_send_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = TwitchGQLClient(_client(handler), FakeIntegritySource())
    with pytest.raises(TwitchGQLRequestError):
        await client.send(GET_CHANNEL, {"login": "x"})


async def test_send_raises_on_non_json_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    client = TwitchGQLClient(_client(handler), FakeIntegritySource())
    with pytest.raises(TwitchGQLRequestError):
        await client.send(GET_CHANNEL, {"login": "x"})


async def test_send_returns_the_parsed_response_when_there_are_no_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"user": {"id": "123"}}})

    client = TwitchGQLClient(_client(handler), FakeIntegritySource())
    result = await client.send(GET_CHANNEL, {"login": "x"})

    assert result == {"data": {"user": {"id": "123"}}}


async def test_send_persisted_includes_integrity_and_user_token():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["client-integrity"] == "fake-integrity-value"
        assert request.headers["authorization"] == "OAuth user-token-abc"
        body = request.content.decode()
        assert "PlaybackAccessToken" in body
        assert "somehash" in body
        return httpx.Response(200, json={"data": {"videoPlaybackAccessToken": {"signature": "s"}}})

    client = TwitchGQLClient(_client(handler), FakeIntegritySource())
    result = await client.send_persisted(
        "PlaybackAccessToken", "somehash", {"vodID": "123"}, user_token="user-token-abc"
    )

    assert result["data"]["videoPlaybackAccessToken"]["signature"] == "s"


async def test_send_persisted_batch_sends_a_list_and_returns_a_list():
    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        assert body.startswith("[")
        return httpx.Response(
            200,
            json=[
                {"data": {"streamPlaybackAccessToken": {"signature": "s1"}}},
                {"data": {"currentUser": {"hasTurbo": False}}},
            ],
        )

    client = TwitchGQLClient(_client(handler), FakeIntegritySource())
    result = await client.send_persisted_batch(
        [
            ("PlaybackAccessToken", "hash1", {"login": "x"}),
            ("AdRequestHandling", "hash2", {"login": "x"}),
        ],
        user_token="user-token-abc",
    )

    assert len(result) == 2
    assert result[0]["data"]["streamPlaybackAccessToken"]["signature"] == "s1"


async def test_send_persisted_raises_on_failed_integrity_check():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"errors": [{"message": "failed integrity check"}]})

    client = TwitchGQLClient(_client(handler), FakeIntegritySource())
    with pytest.raises(TwitchIntegrityCheckFailedError):
        await client.send_persisted("PlaybackAccessToken", "hash", {}, user_token="t")
