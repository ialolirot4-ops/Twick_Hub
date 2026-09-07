"""Playlist use cases."""

from __future__ import annotations

from dataclasses import dataclass

from twitchlink_next.domain.collections import Playlist
from twitchlink_next.domain.protocols import PlaylistRepository
from twitchlink_next.domain.value_objects import Media


class PlaylistNotFoundError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class CreatePlaylistUseCase:
    playlists: PlaylistRepository

    async def execute(self, name: str) -> Playlist:
        playlist = Playlist(name=name)
        await self.playlists.save(playlist)
        return playlist


@dataclass(frozen=True, slots=True)
class AddMediaToPlaylistUseCase:
    playlists: PlaylistRepository

    async def execute(self, playlist_id: str, media: Media) -> Playlist:
        playlist = await self.playlists.get(playlist_id)
        if playlist is None:
            raise PlaylistNotFoundError(playlist_id)

        updated = playlist.with_item_added(media)
        await self.playlists.save(updated)
        return updated
