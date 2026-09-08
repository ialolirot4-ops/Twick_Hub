"""Twitch video provider.

``GetChannelVideos`` (ported from 3.5.5) only accepts a channel *login*,
not the numeric id ``PlatformRef`` carries — Twitch logins can change,
so the numeric id is what the domain model treats as canonical (Favorite,
etc. keep working across a rename). This resolves id → login via
``ChannelDirectory`` first, rather than changing what ``PlatformRef``
stores.
"""

from __future__ import annotations

from twick_hub.domain.content import Video
from twick_hub.domain.protocols import ChannelDirectory
from twick_hub.domain.value_objects import PlatformRef
from twick_hub.infrastructure.twitch.gql.client import TwitchGQLClient
from twick_hub.infrastructure.twitch.gql.errors import TwitchDataNotFoundError
from twick_hub.infrastructure.twitch.gql.mappers import map_video
from twick_hub.infrastructure.twitch.gql.operations import GET_CHANNEL_VIDEOS, GET_VIDEO

_DEFAULT_PAGE_SIZE = 30  # matches TwitchGQLConfig.LOAD_LIMIT in 3.5.5


class TwitchVideoProvider:
    def __init__(self, client: TwitchGQLClient, channel_directory: ChannelDirectory) -> None:
        self._client = client
        self._channel_directory = channel_directory

    async def get_video(self, ref: PlatformRef) -> Video:
        response = await self._client.send(GET_VIDEO, {"id": ref.external_id})
        video = response.get("data", {}).get("video")
        if video is None:
            raise TwitchDataNotFoundError(f"No Twitch video with id {ref.external_id!r}")
        return map_video(video)

    async def list_videos(self, channel_ref: PlatformRef) -> list[Video]:
        channel = await self._channel_directory.get_channel(channel_ref)
        response = await self._client.send(
            GET_CHANNEL_VIDEOS,
            {
                "login": channel.user.username,
                "type": None,
                "sort": "TIME",
                "limit": _DEFAULT_PAGE_SIZE,
                "cursor": None,
            },
        )
        user = response.get("data", {}).get("user")
        if user is None:
            return []
        edges = user.get("videos", {}).get("edges", [])
        return [map_video(edge["node"]) for edge in edges if edge.get("node") is not None]
