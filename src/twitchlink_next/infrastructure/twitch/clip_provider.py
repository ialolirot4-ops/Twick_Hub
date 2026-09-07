"""Twitch clip provider. See video_provider.py's module docstring — the
same id-to-login resolution applies to ``GetChannelClips``.
"""

from __future__ import annotations

from twitchlink_next.domain.content import Clip
from twitchlink_next.domain.protocols import ChannelDirectory
from twitchlink_next.domain.value_objects import PlatformRef
from twitchlink_next.infrastructure.twitch.gql.client import TwitchGQLClient
from twitchlink_next.infrastructure.twitch.gql.errors import TwitchDataNotFoundError
from twitchlink_next.infrastructure.twitch.gql.mappers import map_clip
from twitchlink_next.infrastructure.twitch.gql.operations import GET_CHANNEL_CLIPS, GET_CLIP

_DEFAULT_PAGE_SIZE = 30


class TwitchClipProvider:
    def __init__(self, client: TwitchGQLClient, channel_directory: ChannelDirectory) -> None:
        self._client = client
        self._channel_directory = channel_directory

    async def get_clip(self, ref: PlatformRef) -> Clip:
        response = await self._client.send(GET_CLIP, {"slug": ref.external_id})
        clip = response.get("data", {}).get("clip")
        if clip is None:
            raise TwitchDataNotFoundError(f"No Twitch clip with slug {ref.external_id!r}")
        return map_clip(clip)

    async def list_clips(self, channel_ref: PlatformRef) -> list[Clip]:
        channel = await self._channel_directory.get_channel(channel_ref)
        response = await self._client.send(
            GET_CHANNEL_CLIPS,
            {
                "login": channel.user.username,
                "filter": "ALL_TIME",
                "limit": _DEFAULT_PAGE_SIZE,
                "cursor": None,
            },
        )
        user = response.get("data", {}).get("user")
        if user is None:
            return []
        edges = user.get("clips", {}).get("edges", [])
        return [map_clip(edge["node"]) for edge in edges if edge.get("node") is not None]
