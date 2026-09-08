"""Twitch channel directory and live-stream lookup.

One class implements both ``domain.protocols.ChannelDirectory`` and
``LiveStreamProvider`` because a single GetChannel query already returns
the channel's current stream, if any (ported query, operations.py) — a
second network round trip for live status would be wasteful.
"""

from __future__ import annotations

import re

from twick_hub.domain.content import Stream
from twick_hub.domain.identity import Channel
from twick_hub.domain.value_objects import PlatformRef
from twick_hub.infrastructure.twitch.gql.client import TwitchGQLClient
from twick_hub.infrastructure.twitch.gql.errors import TwitchDataNotFoundError
from twick_hub.infrastructure.twitch.gql.mappers import map_channel, map_stream
from twick_hub.infrastructure.twitch.gql.operations import GET_CHANNEL

# Ported verbatim from TwitchLink 3.5.5's Search/Config.py.
_CHANNEL_LOGIN_RE = re.compile(r"^[a-zA-Z0-9_]+$")
_CHANNEL_URL_RE = re.compile(r"^(?:https?://)?(?:www\.)?twitch\.tv/([a-zA-Z0-9_]+)(?:$|\?|/)")


def _extract_login(query: str) -> str | None:
    query = query.strip()
    if _CHANNEL_LOGIN_RE.match(query):
        return query
    match = _CHANNEL_URL_RE.match(query)
    return match.group(1) if match else None


class TwitchChannelDirectory:
    def __init__(self, client: TwitchGQLClient) -> None:
        self._client = client

    async def find_channel(self, query: str) -> Channel | None:
        login = _extract_login(query)
        if login is None:
            return None
        return await self._lookup(login=login)

    async def get_channel(self, ref: PlatformRef) -> Channel:
        channel = await self._lookup(external_id=ref.external_id)
        if channel is None:
            raise TwitchDataNotFoundError(f"No Twitch channel with id {ref.external_id!r}")
        return channel

    async def get_live_stream(self, channel_ref: PlatformRef) -> Stream | None:
        response = await self._client.send(GET_CHANNEL, {"id": channel_ref.external_id})
        user = response.get("data", {}).get("user")
        if user is None:
            return None
        return map_stream(user, channel_ref)

    async def _lookup(self, login: str = "", external_id: str = "") -> Channel | None:
        response = await self._client.send(GET_CHANNEL, {"id": external_id, "login": login})
        user = response.get("data", {}).get("user")
        # Ported from TwitchGQLAPI.py's `_raiseIfNone`: a deleted/unknown
        # user comes back with id "0", not a null user.
        if user is None or str(user.get("id", "0")) == "0":
            return None
        return map_channel(user)
