"""SQLAlchemy-backed ``UpdateAttemptRepository``. See
channel_repository.py's module docstring for the sync-session-in-a-thread
pattern every repository in this package follows.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from twick_hub.domain.updates import UpdateAttempt
from twick_hub.infrastructure.persistence.mappers import (
    row_to_update_attempt,
    update_attempt_to_row,
)
from twick_hub.infrastructure.persistence.models import UpdateAttemptRow

_DEFAULT_LIST_LIMIT = 500


class SqlUpdateAttemptRepository:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    async def get(self, attempt_id: str) -> UpdateAttempt | None:
        return await asyncio.to_thread(self._get_sync, attempt_id)

    def _get_sync(self, attempt_id: str) -> UpdateAttempt | None:
        with self._session_factory() as session:
            row = session.get(UpdateAttemptRow, attempt_id)
            return row_to_update_attempt(row) if row is not None else None

    async def list_all(self, *, limit: int | None = None, offset: int = 0) -> list[UpdateAttempt]:
        return await asyncio.to_thread(self._list_all_sync, limit, offset)

    def _list_all_sync(self, limit: int | None, offset: int) -> list[UpdateAttempt]:
        with self._session_factory() as session:
            stmt = (
                select(UpdateAttemptRow)
                .order_by(UpdateAttemptRow.started_at.desc())
                .limit(limit or _DEFAULT_LIST_LIMIT)
                .offset(offset)
            )
            rows = session.execute(stmt).scalars().all()
            return [row_to_update_attempt(row) for row in rows]

    async def save(self, attempt: UpdateAttempt) -> None:
        await asyncio.to_thread(self._save_sync, attempt)

    def _save_sync(self, attempt: UpdateAttempt) -> None:
        with self._session_factory() as session:
            session.merge(update_attempt_to_row(attempt))
            session.commit()
