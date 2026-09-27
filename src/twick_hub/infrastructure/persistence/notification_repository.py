"""SQLAlchemy-backed ``NotificationRepository``. See
channel_repository.py's module docstring for the sync-session-in-a-thread
pattern.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select, update
from sqlalchemy.orm import sessionmaker

from twick_hub.domain.notifications import Notification
from twick_hub.infrastructure.persistence.mappers import notification_to_row, row_to_notification
from twick_hub.infrastructure.persistence.models import NotificationRow

_DEFAULT_LIST_LIMIT = 500


class SqlNotificationRepository:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    async def list_unread(self, *, limit: int | None = None, offset: int = 0) -> list[Notification]:
        return await asyncio.to_thread(self._list_unread_sync, limit, offset)

    def _list_unread_sync(self, limit: int | None, offset: int) -> list[Notification]:
        with self._session_factory() as session:
            stmt = (
                select(NotificationRow)
                .where(NotificationRow.is_read.is_(False))
                .order_by(NotificationRow.created_at.desc())
                .limit(limit or _DEFAULT_LIST_LIMIT)
                .offset(offset)
            )
            rows = session.execute(stmt).scalars().all()
            return [row_to_notification(row) for row in rows]

    async def save(self, notification: Notification) -> None:
        await asyncio.to_thread(self._save_sync, notification)

    def _save_sync(self, notification: Notification) -> None:
        with self._session_factory() as session:
            session.merge(notification_to_row(notification))
            session.commit()

    async def mark_read(self, notification_id: str) -> None:
        await asyncio.to_thread(self._mark_read_sync, notification_id)

    def _mark_read_sync(self, notification_id: str) -> None:
        with self._session_factory() as session:
            stmt = (
                update(NotificationRow)
                .where(NotificationRow.id == notification_id)
                .values(is_read=True)
            )
            session.execute(stmt)
            session.commit()
