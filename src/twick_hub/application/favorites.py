"""Favorites use cases.

Depend only on domain protocols — no concrete Infrastructure. FASE 4+
supplies real ``ChannelDirectory``/``FavoriteRepository`` implementations;
tests here use simple in-memory fakes (tests/application/fakes.py).
"""

from __future__ import annotations

from dataclasses import dataclass

from twick_hub.domain.collections import Favorite
from twick_hub.domain.identity import Channel
from twick_hub.domain.protocols import ChannelDirectory, FavoriteRepository
from twick_hub.domain.value_objects import PlatformRef


class ChannelNotFoundError(Exception):
    """Raised when a favorite is requested for a channel the platform
    doesn't recognize. A use case error, not a protocol implementation
    detail — callers (the UI layer) can catch this by name."""


@dataclass(frozen=True, slots=True)
class AddFavoriteUseCase:
    channel_directory: ChannelDirectory
    favorites: FavoriteRepository

    async def execute(
        self, channel_ref: PlatformRef, *, notify_on_live: bool = True, auto_download: bool = False
    ) -> Favorite:
        channel: Channel = await self.channel_directory.get_channel(channel_ref)
        existing = await self.favorites.get_by_channel(channel.ref)
        if existing is not None:
            return existing

        favorite = Favorite(
            channel_ref=channel.ref,
            notify_on_live=notify_on_live,
            auto_download=auto_download,
        )
        await self.favorites.save(favorite)
        return favorite


@dataclass(frozen=True, slots=True)
class RemoveFavoriteUseCase:
    favorites: FavoriteRepository

    async def execute(self, favorite_id: str) -> None:
        await self.favorites.delete(favorite_id)


@dataclass(frozen=True, slots=True)
class ListFavoritesUseCase:
    favorites: FavoriteRepository

    async def execute(self) -> list[Favorite]:
        return await self.favorites.list_all()
