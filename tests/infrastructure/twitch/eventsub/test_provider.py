from __future__ import annotations

import json
from datetime import datetime

import httpx
import pytest
from websockets.exceptions import ConnectionClosedError

from twick_hub.domain.enums import Platform
from twick_hub.domain.events import ChannelWentOffline, ChannelWentOnline, EventBus
from twick_hub.domain.protocols import LiveMonitor
from twick_hub.domain.value_objects import PlatformRef
from twick_hub.infrastructure.twitch.eventsub.errors import (
    CapacityExceededError,
    SubscriptionRejectedError,
)
from twick_hub.infrastructure.twitch.eventsub.provider import TwitchEventSubProvider

_CHANNEL_REF = PlatformRef(platform=Platform.TWITCH, external_id="123")


def _welcome(session_id="sess1", timeout=10) -> str:
    return json.dumps(
        {
            "metadata": {"message_id": f"welcome-{session_id}", "message_type": "session_welcome"},
            "payload": {
                "session": {
                    "id": session_id,
                    "status": "connected",
                    "keepalive_timeout_seconds": timeout,
                    "reconnect_url": None,
                }
            },
        }
    )


def _notification(message_id: str, sub_type: str, broadcaster_id: str = "123") -> str:
    return json.dumps(
        {
            "metadata": {
                "message_id": message_id,
                "message_type": "notification",
                "subscription_type": sub_type,
            },
            "payload": {"event": {"broadcaster_user_id": broadcaster_id}},
        }
    )


def _keepalive(message_id: str) -> str:
    return json.dumps(
        {
            "metadata": {"message_id": message_id, "message_type": "session_keepalive"},
            "payload": {},
        }
    )


def _reconnect(message_id: str, new_session_id: str, url: str) -> str:
    return json.dumps(
        {
            "metadata": {"message_id": message_id, "message_type": "session_reconnect"},
            "payload": {"session": {"id": new_session_id, "reconnect_url": url}},
        }
    )


def _revocation(message_id: str, sub_type: str, broadcaster_id: str = "123") -> str:
    return json.dumps(
        {
            "metadata": {
                "message_id": message_id,
                "message_type": "revocation",
                "subscription_type": sub_type,
            },
            "payload": {"subscription": {"condition": {"broadcaster_user_id": broadcaster_id}}},
        }
    )


class FakeConnection:
    """Yields a scripted sequence of messages. An item that's an
    Exception instance is raised instead of returned — used to simulate
    an abnormal drop (``websockets.exceptions.ConnectionClosedError``).
    """

    def __init__(self, script: list[str | Exception]) -> None:
        self._script = list(script)
        self.closed = False

    async def recv(self) -> str:
        if not self._script:
            raise AssertionError(
                "FakeConnection script exhausted — this test called _receive_and_handle_one() "
                "more times than it scripted messages for. If the test means to exercise an "
                "abnormal disconnect, script a ConnectionClosedError explicitly."
            )
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def close(self) -> None:
        self.closed = True


class FakeConnector:
    """Hands out FakeConnections in order, one per call — lets a test
    script what each successive ``connect()`` call (initial, reconnect,
    post-abnormal-drop) returns."""

    def __init__(self, connections: list[FakeConnection]) -> None:
        self._connections = list(connections)
        self.urls_requested: list[str] = []

    async def __call__(self, url: str) -> FakeConnection:
        self.urls_requested.append(url)
        return self._connections.pop(0)


class FakeLiveStreamProvider:
    async def get_live_stream(self, channel_ref: PlatformRef):
        from twick_hub.domain.content import Stream

        return Stream(
            ref=PlatformRef(platform=Platform.TWITCH, external_id="stream1"),
            channel_ref=channel_ref,
            title="Live now",
            category="Just Chatting",
            started_at=datetime.now(),
            viewer_count=100,
        )


def _http_client(handler=None) -> httpx.AsyncClient:
    if handler is None:

        def _default_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": [{"id": f"sub-{request.url}"}]})

        handler = _default_handler

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _subscription_handler(counter: list[int]):
    def handler(request: httpx.Request) -> httpx.Response:
        counter[0] += 1
        return httpx.Response(200, json={"data": [{"id": f"sub{counter[0]}"}]})

    return handler


def _provider(connector, http_client=None, live_stream_provider=None, token="user-token"):
    return TwitchEventSubProvider(
        http_client or _http_client(),
        live_stream_provider or FakeLiveStreamProvider(),
        lambda: token,
        EventBus(),
        connector=connector,
    )


def test_satisfies_live_monitor_protocol():
    provider = _provider(FakeConnector([FakeConnection([_welcome()])]))
    assert isinstance(provider, LiveMonitor)


async def test_subscribe_creates_two_subscriptions_and_uses_bearer_auth():
    requests_seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(request)
        return httpx.Response(200, json={"data": [{"id": f"sub{len(requests_seen)}"}]})

    connector = FakeConnector([FakeConnection([_welcome()])])
    provider = _provider(connector, http_client=_http_client(handler))
    await provider.subscribe(_CHANNEL_REF)

    assert len(requests_seen) == 2
    assert {r.headers["authorization"] for r in requests_seen} == {"Bearer user-token"}
    types_sent = [json.loads(r.content)["type"] for r in requests_seen]
    assert set(types_sent) == {"stream.online", "stream.offline"}
    assert provider.subscribed_channels == frozenset({_CHANNEL_REF})


async def test_subscribe_beyond_capacity_raises_and_does_not_partially_reserve():
    provider = _provider(FakeConnector([FakeConnection([_welcome()] * 20)]))
    for i in range(5):
        await provider.subscribe(PlatformRef(platform=Platform.TWITCH, external_id=str(i)))

    with pytest.raises(CapacityExceededError):
        await provider.subscribe(PlatformRef(platform=Platform.TWITCH, external_id="overflow"))

    # unchanged — the failed attempt didn't leak a reservation
    assert provider.capacity.used_cost == 10


async def test_subscription_rejected_by_twitch_releases_the_capacity_reservation():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="invalid")

    connector_ = FakeConnector([FakeConnection([_welcome()])])
    provider = _provider(connector_, http_client=_http_client(handler))
    with pytest.raises(SubscriptionRejectedError):
        await provider.subscribe(_CHANNEL_REF)

    assert provider.capacity.used_cost == 0


async def test_unsubscribe_deletes_both_subscriptions():
    delete_requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            delete_requests.append(request)
            return httpx.Response(204)
        return httpx.Response(200, json={"data": [{"id": "subX"}]})

    connector_ = FakeConnector([FakeConnection([_welcome()])])
    provider = _provider(connector_, http_client=_http_client(handler))
    await provider.subscribe(_CHANNEL_REF)
    await provider.unsubscribe(_CHANNEL_REF)

    assert len(delete_requests) == 2
    assert provider.subscribed_channels == frozenset()
    assert provider.capacity.used_cost == 0


async def test_unsubscribe_from_a_channel_never_subscribed_is_a_noop():
    provider = _provider(FakeConnector([FakeConnection([_welcome()])]))
    await provider.unsubscribe(_CHANNEL_REF)  # must not raise


async def test_stream_online_notification_publishes_channel_went_online():
    connection = FakeConnection([_welcome(), _notification("n1", "stream.online")])
    provider = _provider(FakeConnector([connection]))
    seen = []
    provider._event_bus.subscribe(lambda event: seen.append(event))

    await provider._receive_and_handle_one()  # connects (consumes welcome), handles notification

    assert len(seen) == 1
    assert isinstance(seen[0], ChannelWentOnline)
    assert seen[0].channel_ref == _CHANNEL_REF


async def test_stream_offline_notification_publishes_channel_went_offline():
    connection = FakeConnection([_welcome(), _notification("n1", "stream.offline")])
    provider = _provider(FakeConnector([connection]))
    seen = []
    provider._event_bus.subscribe(lambda event: seen.append(event))

    await provider._receive_and_handle_one()

    assert seen == [ChannelWentOffline(_CHANNEL_REF)]


async def test_duplicate_message_id_is_handled_only_once():
    connection = FakeConnection(
        [
            _welcome(),
            _notification("dup1", "stream.offline"),
            _notification("dup1", "stream.offline"),
        ]
    )
    provider = _provider(FakeConnector([connection]))
    seen = []
    provider._event_bus.subscribe(lambda event: seen.append(event))

    await provider._receive_and_handle_one()  # connects, handles first dup1
    await provider._receive_and_handle_one()  # second dup1 — ignored

    assert len(seen) == 1


async def test_keepalive_message_produces_no_event():
    connection = FakeConnection([_welcome(), _keepalive("k1")])
    provider = _provider(FakeConnector([connection]))
    seen = []
    provider._event_bus.subscribe(lambda event: seen.append(event))

    await provider._receive_and_handle_one()

    assert seen == []


async def test_graceful_reconnect_swaps_connection_without_resubscribing():
    old_connection = FakeConnection([_welcome(), _reconnect("r1", "sess2", "wss://new")])
    new_connection = FakeConnection([_welcome(session_id="sess2")])
    connector = FakeConnector([old_connection, new_connection])
    provider = _provider(connector)

    await provider.subscribe(_CHANNEL_REF)  # connects via old_connection's welcome
    subscription_calls_before = connector.urls_requested.copy()

    await provider._receive_and_handle_one()  # the session_reconnect message

    assert old_connection.closed is True
    assert connector.urls_requested == [*subscription_calls_before, "wss://new"]
    # subscriptions were never recreated — same channel, no new HTTP calls needed
    assert provider.subscribed_channels == frozenset({_CHANNEL_REF})


async def test_abnormal_disconnect_reconnects_and_resubscribes():
    sub_counter = [0]
    first_connection = FakeConnection([_welcome(), ConnectionClosedError(None, None)])
    second_connection = FakeConnection([_welcome(session_id="sess2")])
    connector = FakeConnector([first_connection, second_connection])
    provider = _provider(connector, http_client=_http_client(_subscription_handler(sub_counter)))

    await provider.subscribe(_CHANNEL_REF)
    assert sub_counter[0] == 2  # the original online+offline subscriptions

    await provider._receive_and_handle_one()  # hits the ConnectionClosedError → recovers

    assert sub_counter[0] == 4  # re-created online+offline after reconnecting
    assert provider.subscribed_channels == frozenset({_CHANNEL_REF})


async def test_revocation_is_tracked():
    connection = FakeConnection([_welcome(), _revocation("rev1", "stream.online")])
    provider = _provider(FakeConnector([connection]))

    await provider._receive_and_handle_one()

    assert "123:stream.online" in provider.revoked_subscriptions


async def test_stop_closes_the_connection():
    connection = FakeConnection([_welcome()])
    provider = _provider(FakeConnector([connection]))
    await provider.subscribe(_CHANNEL_REF)

    await provider.stop()

    assert connection.closed is True
