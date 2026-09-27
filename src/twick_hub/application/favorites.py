"""Favorites use cases (Master Plan §21/§46, FASE 9).

Depend only on domain protocols plus ``PlatformRegistry`` (FASE 6) — no
concrete Infrastructure. ``AddFavoriteUseCase`` used to take a single
``ChannelDirectory`` (FASE 3, one platform only); FASE 9 explicitly
requires "Soportar Twitch + Kick" for every Favorites function, so it now
takes a ``PlatformRegistry`` and dispatches by ``channel_ref.platform``
(see docs/architecture-decisions.md's FASE 9 entry — this is the
RISK-ARCH-02 fix, triggered by this phase's own requirement, not done
"por comodidad").
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from twick_hub.application.platform_registry import PlatformRegistry
from twick_hub.domain.collections import Favorite
from twick_hub.domain.content import Stream
from twick_hub.domain.protocols import FavoriteRepository
from twick_hub.domain.value_objects import PlatformRef


class ChannelNotFoundError(Exception):
    """Raised when a favorite is requested for a channel the platform
    doesn't recognize. A use case error, not a protocol implementation
    detail — callers (the UI layer) can catch this by name."""


@dataclass(frozen=True, slots=True)
class AddFavoriteUseCase:
    registry: PlatformRegistry
    favorites: FavoriteRepository

    async def execute(
        self,
        channel_ref: PlatformRef,
        *,
        notify_on_live: bool = True,
        auto_download: bool = False,
        preferred_quality: str | None = None,
        preferred_format: str | None = None,
        download_directory: str | None = None,
    ) -> Favorite:
        channel = await self.registry.get_channel(channel_ref)
        existing = await self.favorites.get_by_channel(channel.ref)
        if existing is not None:
            return existing

        existing_favorites = await self.favorites.list_all()
        favorite = Favorite(
            channel_ref=channel.ref,
            notify_on_live=notify_on_live,
            auto_download=auto_download,
            preferred_quality=preferred_quality,
            preferred_format=preferred_format,
            download_directory=download_directory,
            position=len(existing_favorites),
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


@dataclass(frozen=True, slots=True)
class UpdateFavoriteSettingsUseCase:
    """Master Plan §21's per-favorite settings — notification, auto-
    download (the flag only; FASE 11's AutoDownloadRule owns the actual
    triggering behavior, see docs/functional-baseline.md), preferred
    quality/format, and download directory. Every parameter is optional
    so a caller only changes what the person actually edited."""

    favorites: FavoriteRepository

    async def execute(
        self,
        favorite_id: str,
        *,
        notify_on_live: bool | None = None,
        auto_download: bool | None = None,
        preferred_quality: str | None = "__unset__",
        preferred_format: str | None = "__unset__",
        download_directory: str | None = "__unset__",
    ) -> Favorite:
        existing = await self._get_or_raise(favorite_id)
        updated = replace(
            existing,
            notify_on_live=existing.notify_on_live if notify_on_live is None else notify_on_live,
            auto_download=existing.auto_download if auto_download is None else auto_download,
            preferred_quality=(
                existing.preferred_quality
                if preferred_quality == "__unset__"
                else preferred_quality
            ),
            preferred_format=(
                existing.preferred_format if preferred_format == "__unset__" else preferred_format
            ),
            download_directory=(
                existing.download_directory
                if download_directory == "__unset__"
                else download_directory
            ),
        )
        await self.favorites.save(updated)
        return updated

    async def _get_or_raise(self, favorite_id: str) -> Favorite:
        for favorite in await self.favorites.list_all():
            if favorite.id == favorite_id:
                return favorite
        raise LookupError(f"no such favorite: {favorite_id}")


@dataclass(frozen=True, slots=True)
class ReorderFavoritesUseCase:
    """FASE 9's "reorder" function. ``ordered_ids`` is the complete new
    order, front to back — position 0 is first. Any existing favorite
    whose id is missing from ``ordered_ids`` keeps its old position
    (defensive: a stale client payload shouldn't silently drop a
    favorite's place)."""

    favorites: FavoriteRepository

    async def execute(self, ordered_ids: list[str]) -> list[Favorite]:
        position_by_id = {favorite_id: index for index, favorite_id in enumerate(ordered_ids)}
        current = await self.favorites.list_all()
        updated: list[Favorite] = []
        for favorite in current:
            if favorite.id in position_by_id:
                favorite = replace(favorite, position=position_by_id[favorite.id])
                await self.favorites.save(favorite)
            updated.append(favorite)
        return sorted(updated, key=lambda f: f.position)


@dataclass(frozen=True, slots=True)
class FavoriteLiveState:
    favorite: Favorite
    stream: Stream | None

    @property
    def is_live(self) -> bool:
        return self.stream is not None


@dataclass(frozen=True, slots=True)
class GetFavoritesLiveStateUseCase:
    """FASE 9's "live state" function, tying persistence (FASE 8) to the
    unified Platform Layer (FASE 6) — exactly what §46's "ENTRADA
    AUTÓNOMA: persistence + platform layer" describes. A platform with no
    LiveStreamProvider (Kick, today) reports every one of its favorites
    as not live rather than erroring — same as
    ``PlatformRegistry.get_live_stream`` itself."""

    favorites: FavoriteRepository
    registry: PlatformRegistry

    async def execute(self) -> list[FavoriteLiveState]:
        all_favorites = await self.favorites.list_all()
        return [
            FavoriteLiveState(
                favorite=favorite, stream=await self.registry.get_live_stream(favorite.channel_ref)
            )
            for favorite in all_favorites
        ]
