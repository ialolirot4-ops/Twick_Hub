"""SQLAlchemy-backed ``FavoriteRepository``. See channel_repository.py's
module docstring for the sync-session-in-a-thread pattern every
repository in this package follows.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from twick_hub.domain.collections import Favorite
from twick_hub.domain.value_objects import PlatformRef
from twick_hub.infrastructure.persistence.mappers import favorite_to_row, row_to_favorite
from twick_hub.infrastructure.persistence.models import FavoriteRow

# Master Plan §45: "No cargar miles de registros sin necesidad" — applied
# even when a caller doesn't pass an explicit limit, not just when one is
# given (the same default appears in every repository in this package).
_DEFAULT_LIST_LIMIT = 500


class SqlFavoriteRepository:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    async def list_all(self, *, limit: int | None = None, offset: int = 0) -> list[Favorite]:
        return await asyncio.to_thread(self._list_all_sync, limit, offset)

    def _list_all_sync(self, limit: int | None, offset: int) -> list[Favorite]:
        with self._session_factory() as session:
            stmt = (
                select(FavoriteRow)
                .order_by(FavoriteRow.position.asc())
                .limit(limit or _DEFAULT_LIST_LIMIT)
                .offset(offset)
            )
            rows = session.execute(stmt).scalars().all()
            return [row_to_favorite(row) for row in rows]

    async def get_by_channel(self, channel_ref: PlatformRef) -> Favorite | None:
        return await asyncio.to_thread(self._get_by_channel_sync, channel_ref)

    def _get_by_channel_sync(self, channel_ref: PlatformRef) -> Favorite | None:
        with self._session_factory() as session:
            stmt = select(FavoriteRow).where(
                FavoriteRow.channel_platform == channel_ref.platform.value,
                FavoriteRow.channel_external_id == channel_ref.external_id,
            )
            row = session.execute(stmt).scalars().first()
            return row_to_favorite(row) if row is not None else None

    async def save(self, favorite: Favorite) -> None:
        await asyncio.to_thread(self._save_sync, favorite)

    def _save_sync(self, favorite: Favorite) -> None:
        with self._session_factory() as session:
            session.merge(favorite_to_row(favorite))
            session.commit()

    async def delete(self, favorite_id: str) -> None:
        await asyncio.to_thread(self._delete_sync, favorite_id)

    def _delete_sync(self, favorite_id: str) -> None:
        with self._session_factory() as session:
            row = session.get(FavoriteRow, favorite_id)
            if row is not None:
                session.delete(row)
                session.commit()
