"""Twitch EventSub WebSocket provider — implements
``domain.protocols.LiveMonitor``.

``_receive_and_handle_one`` is the actual unit of work (receive one
message, dedupe it, dispatch it) — deliberately separated from the
infinite ``run_forever`` loop so tests can drive it one message at a
time with a scripted fake connection, instead of racing a real
background task. Master Plan §41: "No conectar EventSub directamente
con UI" — this only ever publishes onto ``domain.events.EventBus``;
nothing here imports PySide6 or touches ``presentation/``.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from collections.abc import Callable

import httpx
from websockets.exceptions import ConnectionClosed

from twick_hub.domain.enums import Platform
from twick_hub.domain.events import ChannelWentOffline, ChannelWentOnline, EventBus
from twick_hub.domain.monitoring import MonitorStats
from twick_hub.domain.protocols import LiveStreamProvider
from twick_hub.domain.value_objects import PlatformRef
from twick_hub.infrastructure.twitch.config import WEB_CLIENT_ID
from twick_hub.infrastructure.twitch.eventsub.capacity import CapacityGovernor
from twick_hub.infrastructure.twitch.eventsub.config import (
    EVENTSUB_SUBSCRIPTIONS_URL,
    EVENTSUB_WEBSOCKET_URL,
    KEEPALIVE_GRACE_SECONDS,
    STREAM_OFFLINE,
    STREAM_ONLINE,
)
from twick_hub.infrastructure.twitch.eventsub.connection import (
    WebSocketConnection,
    connect_real,
)
from twick_hub.infrastructure.twitch.eventsub.errors import (
    ConnectionLostError,
    SubscriptionRejectedError,
)
from twick_hub.infrastructure.twitch.eventsub.messages import (
    broadcaster_ref_of,
    keepalive_timeout_of,
    parse_message,
    reconnect_url_of,
    session_id_of,
)

logger = logging.getLogger(__name__)

_DEDUP_WINDOW = 1000  # recent message_ids remembered — Twitch's own guidance: dedupe on message_id


class TwitchEventSubProvider:
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        live_stream_provider: LiveStreamProvider,
        user_token_getter,
        event_bus: EventBus,
        connector=connect_real,
    ) -> None:
        self._http = http_client
        self._live_stream_provider = live_stream_provider
        self._get_user_token = user_token_getter
        self._event_bus = event_bus
        self._connector = connector
        self.capacity = CapacityGovernor()

        self._connection: WebSocketConnection | None = None
        self._session_id: str | None = None
        self._keepalive_timeout: int | None = None
        self._seen_message_ids: deque[str] = deque(maxlen=_DEDUP_WINDOW)
        self._subscription_ids: dict[PlatformRef, tuple[str, str]] = {}
        self._revoked: set[str] = set()
        self._run_task: asyncio.Task | None = None

        # FASE 10: consumption metrics, and state that has to survive a
        # failed reconnect attempt.
        self._requests = 0
        self._errors = 0
        self._reconnects = 0
        self._abnormal_disconnects = 0
        self._connected_once = False
        self._stopped = False
        self._pending_resubscribe: set[PlatformRef] = set()
        self._push_lost_handlers: list[Callable[[PlatformRef], None]] = []

    @property
    def subscribed_channels(self) -> frozenset[PlatformRef]:
        return frozenset(self._subscription_ids)

    async def subscribe(self, channel_ref: PlatformRef) -> None:
        self.capacity.reserve(channel_ref)
        try:
            await self._ensure_connected()
            online_id = await self._create_subscription(STREAM_ONLINE, channel_ref)
            offline_id = await self._create_subscription(STREAM_OFFLINE, channel_ref)
        except Exception:
            self.capacity.release(channel_ref)
            raise
        self._subscription_ids[channel_ref] = (online_id, offline_id)

    def stats(self) -> MonitorStats:
        return MonitorStats(
            requests=self._requests,
            errors=self._errors,
            reconnects=self._reconnects,
            abnormal_disconnects=self._abnormal_disconnects,
            channels_watched=len(self._subscription_ids) + len(self._pending_resubscribe),
        )

    def on_push_lost(self, handler: Callable[[PlatformRef], None]) -> None:
        """Registers who to tell when Twitch revokes a channel's
        subscription (``domain.monitoring.PushLossNotifier``). What to do
        about it — FASE 4d deliberately left that undecided — is the
        registrant's policy (the hybrid monitor falls back to polling)."""
        self._push_lost_handlers.append(handler)

    async def unsubscribe(self, channel_ref: PlatformRef) -> None:
        self._pending_resubscribe.discard(channel_ref)
        ids = self._subscription_ids.pop(channel_ref, None)
        self.capacity.release(channel_ref)
        if ids is None:
            return
        for subscription_id in ids:
            await self._delete_subscription(subscription_id)

    async def run_forever(self) -> None:
        """Production entry point — keeps receiving and handling
        messages, transparently reconnecting on an abnormal drop,
        until cancelled.
        """
        while not self._stopped:
            await self._receive_and_handle_one()

    async def stop(self) -> None:
        """Terminal: closes the socket and makes ``run_forever`` return
        (instead of treating the close as a drop and reconnecting)."""
        self._stopped = True
        if self._connection is not None:
            await self._connection.close()
        self._connection = None

    async def _receive_and_handle_one(self) -> None:
        await self._ensure_connected()
        await self._resubscribe_pending()
        assert self._connection is not None
        assert self._keepalive_timeout is not None

        try:
            raw_text = await asyncio.wait_for(
                self._connection.recv(), timeout=self._keepalive_timeout + KEEPALIVE_GRACE_SECONDS
            )
        except (TimeoutError, ConnectionClosed):
            if self._stopped:
                return  # we closed it ourselves; not a drop to recover from
            await self._recover_from_abnormal_disconnect()
            return

        message = parse_message(json.loads(raw_text))
        if message.message_id in self._seen_message_ids:
            return  # duplicate protection
        self._seen_message_ids.append(message.message_id)

        if message.message_type == "session_keepalive":
            return
        if message.message_type == "notification":
            await self._handle_notification(message.subscription_type, broadcaster_ref_of(message))
        elif message.message_type == "session_reconnect":
            await self._handle_graceful_reconnect(reconnect_url_of(message))
        elif message.message_type == "revocation":
            self._handle_revocation(message.subscription_type, broadcaster_ref_of(message))

    async def _handle_notification(
        self, subscription_type: str | None, broadcaster_id: str
    ) -> None:
        channel_ref = PlatformRef(platform=Platform.TWITCH, external_id=broadcaster_id)
        if subscription_type == "stream.online":
            try:
                stream = await self._live_stream_provider.get_live_stream(channel_ref)
            except Exception:
                # Never let a failed details lookup kill the receive loop.
                # The go-live is not lost for good: the hybrid monitor's
                # slow reconcile poll re-checks push-covered channels.
                self._errors += 1
                logger.warning(
                    "stream.online for %s: details lookup failed", channel_ref, exc_info=True
                )
                return
            if stream is not None:
                await self._event_bus.publish(ChannelWentOnline(channel_ref, stream))
        elif subscription_type == "stream.offline":
            await self._event_bus.publish(ChannelWentOffline(channel_ref))

    async def _handle_graceful_reconnect(self, new_url: str) -> None:
        old_connection = self._connection
        await self._open_connection(new_url)  # subscriptions carry over — nothing to recreate
        if old_connection is not None:
            await old_connection.close()

    def _handle_revocation(self, subscription_type: str | None, broadcaster_id: str) -> None:
        # Tracked so a caller can inspect it; what to do about it is the
        # registered handlers' policy (Master Plan permanent rule: no
        # asumir) — see ``on_push_lost``.
        self._revoked.add(f"{broadcaster_id}:{subscription_type}")
        channel_ref = PlatformRef(platform=Platform.TWITCH, external_id=broadcaster_id)
        for handler in list(self._push_lost_handlers):
            handler(channel_ref)

    @property
    def revoked_subscriptions(self) -> frozenset[str]:
        return frozenset(self._revoked)

    async def _recover_from_abnormal_disconnect(self) -> None:
        self._abnormal_disconnects += 1
        self._connection = None
        # Kept in ``_pending_resubscribe`` until re-created, not in a
        # local: if opening the new connection fails, the next attempt
        # (the loop's supervisor retries) must still know which channels
        # need their subscriptions back. FASE 10 fix — before it, a failed
        # reconnect here forgot every channel and left it silently
        # unmonitored while still counted against the capacity budget.
        self._pending_resubscribe.update(self._subscription_ids)
        self._subscription_ids.clear()
        await self._ensure_connected()
        await self._resubscribe_pending()

    async def _resubscribe_pending(self) -> None:
        for channel_ref in list(self._pending_resubscribe):
            online_id = await self._create_subscription(STREAM_ONLINE, channel_ref)
            offline_id = await self._create_subscription(STREAM_OFFLINE, channel_ref)
            self._subscription_ids[channel_ref] = (online_id, offline_id)
            self._pending_resubscribe.discard(channel_ref)

    async def _ensure_connected(self) -> None:
        if self._connection is None:
            await self._open_connection(EVENTSUB_WEBSOCKET_URL)

    async def _open_connection(self, url: str) -> None:
        connection = await self._connector(url)
        message = parse_message(json.loads(await connection.recv()))
        if message.message_type != "session_welcome":
            raise ConnectionLostError(f"Expected session_welcome, got {message.message_type!r}")
        self._connection = connection
        self._session_id = session_id_of(message)
        self._keepalive_timeout = keepalive_timeout_of(message)
        if self._connected_once:
            self._reconnects += 1
        self._connected_once = True

    async def _create_subscription(
        self, subscription: tuple[str, str], channel_ref: PlatformRef
    ) -> str:
        sub_type, version = subscription
        token = self._get_user_token()
        self._requests += 1
        response = await self._http.post(
            EVENTSUB_SUBSCRIPTIONS_URL,
            json={
                "type": sub_type,
                "version": version,
                "condition": {"broadcaster_user_id": channel_ref.external_id},
                "transport": {"method": "websocket", "session_id": self._session_id},
            },
            headers={"Client-Id": WEB_CLIENT_ID, "Authorization": f"Bearer {token}"},
        )
        if response.status_code >= 400:
            self._errors += 1
            raise SubscriptionRejectedError(
                f"Twitch rejected {sub_type} for {channel_ref.external_id!r}: {response.text}"
            )
        return response.json()["data"][0]["id"]

    async def _delete_subscription(self, subscription_id: str) -> None:
        token = self._get_user_token()
        self._requests += 1
        await self._http.delete(
            EVENTSUB_SUBSCRIPTIONS_URL,
            params={"id": subscription_id},
            headers={"Client-Id": WEB_CLIENT_ID, "Authorization": f"Bearer {token}"},
        )
