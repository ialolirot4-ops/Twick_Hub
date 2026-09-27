"""SQLAlchemy-backed ``PlaylistRepository``. See channel_repository.py's
module docstring for the sync-session-in-a-thread pattern.

``PlaylistRow.items`` cascades "all, delete-orphan": a merge()'d Playlist
whose items grew (``Playlist.with_item_added``) or shrank/reordered
(``with_item_removed``/``with_items_reordered``, FASE 12) is expected to
insert, delete, and renumber rows correctly through a plain ``merge()`` —
verified by tests/infrastructure/persistence/test_playlist_repository.py,
including that a removed item's row is actually gone from the database,
not just detached from the in-memory collection.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.orm import selectinload, sessionmaker

from twick_hub.domain.collections import Playlist
from twick_hub.infrastructure.persistence.mappers import playlist_to_row, row_to_playlist
from twick_hub.infrastructure.persistence.models import PlaylistRow

_DEFAULT_LIST_LIMIT = 500


class SqlPlaylistRepository:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    async def list_all(self, *, limit: int | None = None, offset: int = 0) -> list[Playlist]:
        return await asyncio.to_thread(self._list_all_sync, limit, offset)

    def _list_all_sync(self, limit: int | None, offset: int) -> list[Playlist]:
        with self._session_factory() as session:
            stmt = (
                select(PlaylistRow)
                .options(selectinload(PlaylistRow.items))
                .order_by(PlaylistRow.created_at.desc())
                .limit(limit or _DEFAULT_LIST_LIMIT)
                .offset(offset)
            )
            rows = session.execute(stmt).scalars().all()
            return [row_to_playlist(row) for row in rows]

    async def get(self, playlist_id: str) -> Playlist | None:
        return await asyncio.to_thread(self._get_sync, playlist_id)

    def _get_sync(self, playlist_id: str) -> Playlist | None:
        with self._session_factory() as session:
            stmt = (
                select(PlaylistRow)
                .options(selectinload(PlaylistRow.items))
                .where(PlaylistRow.id == playlist_id)
            )
            row = session.execute(stmt).scalars().first()
            return row_to_playlist(row) if row is not None else None

    async def save(self, playlist: Playlist) -> None:
        await asyncio.to_thread(self._save_sync, playlist)

    def _save_sync(self, playlist: Playlist) -> None:
        with self._session_factory() as session:
            session.merge(playlist_to_row(playlist))
            session.commit()

    async def delete(self, playlist_id: str) -> None:
        await asyncio.to_thread(self._delete_sync, playlist_id)

    def _delete_sync(self, playlist_id: str) -> None:
        with self._session_factory() as session:
            row = session.get(PlaylistRow, playlist_id)
            if row is not None:
                session.delete(row)
                session.commit()
