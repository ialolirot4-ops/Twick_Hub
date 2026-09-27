"""SQLAlchemy-backed ``SettingsRepository``. See channel_repository.py's
module docstring for the sync-session-in-a-thread pattern every
repository in this package follows.

``get()`` never returns ``None`` — a fresh install has no ``settings``
row yet, so it returns ``Settings()`` (the defaults) without touching the
database to write one; the row only appears once something actually
calls ``save()``. This mirrors ``AppConfig``'s own "runs with zero
configuration" philosophy (see domain/settings.py's module docstring).
"""

from __future__ import annotations

import asyncio

from sqlalchemy.orm import sessionmaker

from twick_hub.domain.settings import SETTINGS_ID, Settings
from twick_hub.infrastructure.persistence.mappers import row_to_settings, settings_to_row
from twick_hub.infrastructure.persistence.models import SettingsRow


class SqlSettingsRepository:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    async def get(self) -> Settings:
        return await asyncio.to_thread(self._get_sync)

    def _get_sync(self) -> Settings:
        with self._session_factory() as session:
            row = session.get(SettingsRow, SETTINGS_ID)
            return row_to_settings(row) if row is not None else Settings()

    async def save(self, settings: Settings) -> None:
        await asyncio.to_thread(self._save_sync, settings)

    def _save_sync(self, settings: Settings) -> None:
        with self._session_factory() as session:
            session.merge(settings_to_row(settings))
            session.commit()
