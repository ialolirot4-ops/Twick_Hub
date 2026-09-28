"""Favorites page bridge (FASE 21b): ``ListFavoritesUseCase`` +
``GetFavoritesLiveStateUseCase`` over the real ``SqlFavoriteRepository``.

Loading is two-phase on purpose. Phase 1 lists favorites straight from
SQLite and shows them at once with ``liveState == "unknown"``. Phase 2
asks the ``PlatformRegistry`` for live status and only then flips rows to
``"live"``/``"offline"``. A platform with no live adapter (both, until
FASE 21c) — or a live check that raises — leaves its rows ``"unknown"``:
the page degrades, it never fails, and never claims \"offline\" for a
channel nobody could check.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Slot

from twick_hub.application.favorites import (
    GetFavoritesLiveStateUseCase,
    ListFavoritesUseCase,
)
from twick_hub.application.platform_registry import PlatformRegistry
from twick_hub.domain.collections import Favorite
from twick_hub.domain.protocols import FavoriteRepository
from twick_hub.presentation.qml_bridge.row_model import Row, RowListModel
from twick_hub.presentation.qml_bridge.tasks import TaskRunner

logger = logging.getLogger(__name__)

LIVE = "live"
OFFLINE = "offline"
UNKNOWN = "unknown"


def _row(favorite: Favorite, live_state: str) -> Row:
    return {
        "id": favorite.id,
        # Favorites persist only a channel_ref (no display name — the channel
        # cache isn't populated until 21c/21d), so the platform's own id is
        # the honest label for now.
        "channelName": favorite.channel_ref.external_id,
        "platform": favorite.channel_ref.platform.value,
        "liveState": live_state,
    }


class FavoritesModel(RowListModel):
    ROLES = ("id", "channelName", "platform", "liveState")

    def __init__(
        self,
        favorites: FavoriteRepository,
        registry: PlatformRegistry,
        runner: TaskRunner,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(self.ROLES, parent)
        self._list = ListFavoritesUseCase(favorites)
        self._live_state = GetFavoritesLiveStateUseCase(favorites, registry)
        self._registry = registry
        self._runner = runner

    @Slot()
    def refresh(self) -> None:
        self._runner.run(self.reload())

    async def reload(self) -> None:
        favorites = await self._list.execute()
        self.replace_rows([_row(f, UNKNOWN) for f in favorites])
        if not any(self._can_check_live(f) for f in favorites):
            return
        try:
            states = await self._live_state.execute()
        except Exception:
            logger.warning("Live-state check failed; showing favorites as unknown", exc_info=True)
            return
        self.replace_rows([_row(s.favorite, self._state_of(s.favorite, s.is_live)) for s in states])

    def _can_check_live(self, favorite: Favorite) -> bool:
        platform = favorite.channel_ref.platform
        return (
            self._registry.is_registered(platform)
            and self._registry.capabilities_for(platform).has_live
        )

    def _state_of(self, favorite: Favorite, is_live: bool) -> str:
        if not self._can_check_live(favorite):
            return UNKNOWN
        return LIVE if is_live else OFFLINE
