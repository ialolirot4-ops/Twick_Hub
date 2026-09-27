"""SQLAlchemy-backed ``DownloadRepository``. See channel_repository.py's
module docstring for the sync-session-in-a-thread pattern.
"""

from __future__ import annotations

import asyncio
from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from twick_hub.domain.downloads import Download
from twick_hub.domain.enums import DownloadStatus
from twick_hub.infrastructure.persistence.mappers import download_to_row, row_to_download
from twick_hub.infrastructure.persistence.models import DownloadRow

_DEFAULT_LIST_LIMIT = 500


class SqlDownloadRepository:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    async def list_all(self, *, limit: int | None = None, offset: int = 0) -> list[Download]:
        return await asyncio.to_thread(self._list_all_sync, limit, offset)

    def _list_all_sync(self, limit: int | None, offset: int) -> list[Download]:
        with self._session_factory() as session:
            stmt = (
                select(DownloadRow)
                .order_by(DownloadRow.created_at.desc())
                .limit(limit or _DEFAULT_LIST_LIMIT)
                .offset(offset)
            )
            rows = session.execute(stmt).scalars().all()
            return [row_to_download(row) for row in rows]

    async def list_by_status(self, statuses: Collection[DownloadStatus]) -> list[Download]:
        """Uncapped on purpose (unlike ``list_all``): callers ask for a
        handful of non-terminal states — restart recovery — never the
        history, so the result is small by construction."""
        return await asyncio.to_thread(self._list_by_status_sync, [s.value for s in statuses])

    def _list_by_status_sync(self, statuses: list[str]) -> list[Download]:
        with self._session_factory() as session:
            stmt = (
                select(DownloadRow)
                .where(DownloadRow.status.in_(statuses))
                .order_by(DownloadRow.created_at)
            )
            return [row_to_download(row) for row in session.execute(stmt).scalars().all()]

    async def get(self, download_id: str) -> Download | None:
        return await asyncio.to_thread(self._get_sync, download_id)

    def _get_sync(self, download_id: str) -> Download | None:
        with self._session_factory() as session:
            row = session.get(DownloadRow, download_id)
            return row_to_download(row) if row is not None else None

    async def save(self, download: Download) -> None:
        await asyncio.to_thread(self._save_sync, download)

    def _save_sync(self, download: Download) -> None:
        with self._session_factory() as session:
            session.merge(download_to_row(download))
            session.commit()
