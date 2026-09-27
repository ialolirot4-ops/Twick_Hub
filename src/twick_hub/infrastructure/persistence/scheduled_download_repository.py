"""SQLAlchemy-backed ``ScheduledDownloadRepository``. See
channel_repository.py's module docstring for the sync-session-in-a-thread
pattern.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from twick_hub.domain.collections import ScheduledDownload
from twick_hub.infrastructure.persistence.mappers import (
    row_to_scheduled_download,
    scheduled_download_to_row,
)
from twick_hub.infrastructure.persistence.models import ScheduledDownloadRow

_DEFAULT_LIST_LIMIT = 500


class SqlScheduledDownloadRepository:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    async def list_all(
        self, *, limit: int | None = None, offset: int = 0
    ) -> list[ScheduledDownload]:
        return await asyncio.to_thread(self._list_all_sync, limit, offset)

    def _list_all_sync(self, limit: int | None, offset: int) -> list[ScheduledDownload]:
        with self._session_factory() as session:
            stmt = (
                select(ScheduledDownloadRow)
                .order_by(ScheduledDownloadRow.created_at.desc())
                .limit(limit or _DEFAULT_LIST_LIMIT)
                .offset(offset)
            )
            rows = session.execute(stmt).scalars().all()
            return [row_to_scheduled_download(row) for row in rows]

    async def save(self, scheduled: ScheduledDownload) -> None:
        await asyncio.to_thread(self._save_sync, scheduled)

    def _save_sync(self, scheduled: ScheduledDownload) -> None:
        with self._session_factory() as session:
            session.merge(scheduled_download_to_row(scheduled))
            session.commit()

    async def delete(self, scheduled_id: str) -> None:
        await asyncio.to_thread(self._delete_sync, scheduled_id)

    def _delete_sync(self, scheduled_id: str) -> None:
        with self._session_factory() as session:
            row = session.get(ScheduledDownloadRow, scheduled_id)
            if row is not None:
                session.delete(row)
                session.commit()
