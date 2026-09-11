"""Kick channel directory and live-stream lookup — implements
``domain.protocols.ChannelDirectory`` and ``LiveStreamProvider``, the
same pair ``TwitchChannelDirectory`` implements (docs/architecture-
decisions.md AD-14's segregated protocols: a Kick adapter implements
what Kick can actually back, nothing more).
"""

from __future__ import annotations

from twick_hub.domain.content import Stream
from twick_hub.domain.identity import Channel
from twick_hub.domain.value_objects import PlatformRef
from twick_hub.infrastructure.kick.client import KickAPIClient
from twick_hub.infrastructure.kick.errors import KickDataNotFoundError
from twick_hub.infrastructure.kick.mappers import map_channel, map_live_stream


class KickChannelDirectory:
    def __init__(self, client: KickAPIClient) -> None:
        self._client = client

    async def find_channel(self, query: str) -> Channel | None:
        # Kick channel slugs are the same shape as Twitch logins
        # (lowercase alphanumeric + separators) — a bare slug or a
        # kick.com/<slug> URL. Only the exact-slug case is implemented
        # here since /channels only takes a slug or id; a fuzzy
        # by-name search isn't in Kick's official API (docs/kick-audit.md).
        slug = _extract_slug(query)
        if slug is None:
            return None
        data = await self._client.get_channel_by_slug(slug)
        return map_channel(data) if data is not None else None

    async def get_channel(self, ref: PlatformRef) -> Channel:
        data = await self._client.get_channel_by_broadcaster_id(ref.external_id)
        if data is None:
            raise KickDataNotFoundError(f"No Kick channel with id {ref.external_id!r}")
        return map_channel(data)

    async def get_live_stream(self, channel_ref: PlatformRef) -> Stream | None:
        data = await self._client.get_livestream(channel_ref.external_id)
        return map_live_stream(data) if data is not None else None


def _extract_slug(query: str) -> str | None:
    query = query.strip()
    if query.replace("_", "").replace("-", "").isalnum():
        return query
    prefix_variants = ("https://kick.com/", "http://kick.com/", "kick.com/", "www.kick.com/")
    for prefix in prefix_variants:
        if query.lower().startswith(prefix):
            return query[len(prefix) :].split("/")[0].split("?")[0]
    return None
