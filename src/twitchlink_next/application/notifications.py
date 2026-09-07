"""Notification use cases."""

from __future__ import annotations

from dataclasses import dataclass

from twitchlink_next.domain.notifications import Notification
from twitchlink_next.domain.protocols import NotificationRepository


@dataclass(frozen=True, slots=True)
class ListUnreadNotificationsUseCase:
    notifications: NotificationRepository

    async def execute(self) -> list[Notification]:
        return await self.notifications.list_unread()


@dataclass(frozen=True, slots=True)
class MarkNotificationReadUseCase:
    notifications: NotificationRepository

    async def execute(self, notification_id: str) -> None:
        await self.notifications.mark_read(notification_id)
