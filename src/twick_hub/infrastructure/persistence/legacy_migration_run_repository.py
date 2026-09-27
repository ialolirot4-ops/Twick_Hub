"""SQLAlchemy-backed ``LegacyMigrationRunRepository``. See
channel_repository.py's module docstring for the sync-session-in-a-thread
pattern every repository in this package follows.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from twick_hub.domain.migration import LegacyMigrationRun
from twick_hub.infrastructure.persistence.mappers import (
    legacy_migration_run_to_row,
    row_to_legacy_migration_run,
)
from twick_hub.infrastructure.persistence.models import LegacyMigrationRunRow

_DEFAULT_LIST_LIMIT = 500


class SqlLegacyMigrationRunRepository:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    async def get(self, run_id: str) -> LegacyMigrationRun | None:
        return await asyncio.to_thread(self._get_sync, run_id)

    def _get_sync(self, run_id: str) -> LegacyMigrationRun | None:
        with self._session_factory() as session:
            row = session.get(LegacyMigrationRunRow, run_id)
            return row_to_legacy_migration_run(row) if row is not None else None

    async def list_all(
        self, *, limit: int | None = None, offset: int = 0
    ) -> list[LegacyMigrationRun]:
        return await asyncio.to_thread(self._list_all_sync, limit, offset)

    def _list_all_sync(self, limit: int | None, offset: int) -> list[LegacyMigrationRun]:
        with self._session_factory() as session:
            stmt = (
                select(LegacyMigrationRunRow)
                .order_by(LegacyMigrationRunRow.started_at.desc())
                .limit(limit or _DEFAULT_LIST_LIMIT)
                .offset(offset)
            )
            rows = session.execute(stmt).scalars().all()
            return [row_to_legacy_migration_run(row) for row in rows]

    async def find_by_source_hash(self, source_sha256: str) -> LegacyMigrationRun | None:
        return await asyncio.to_thread(self._find_by_source_hash_sync, source_sha256)

    def _find_by_source_hash_sync(self, source_sha256: str) -> LegacyMigrationRun | None:
        with self._session_factory() as session:
            stmt = (
                select(LegacyMigrationRunRow)
                .where(LegacyMigrationRunRow.source_sha256 == source_sha256)
                .order_by(LegacyMigrationRunRow.started_at.desc())
            )
            row = session.execute(stmt).scalars().first()
            return row_to_legacy_migration_run(row) if row is not None else None

    async def save(self, run: LegacyMigrationRun) -> None:
        await asyncio.to_thread(self._save_sync, run)

    def _save_sync(self, run: LegacyMigrationRun) -> None:
        with self._session_factory() as session:
            session.merge(legacy_migration_run_to_row(run))
            session.commit()
