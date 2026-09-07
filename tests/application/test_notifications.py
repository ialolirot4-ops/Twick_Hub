from tests.application.fakes import InMemoryNotificationRepository
from twitchlink_next.application.notifications import (
    ListUnreadNotificationsUseCase,
    MarkNotificationReadUseCase,
)
from twitchlink_next.domain.enums import NotificationKind
from twitchlink_next.domain.notifications import Notification


async def test_list_unread_excludes_read_notifications():
    notifications = InMemoryNotificationRepository()
    unread = Notification(
        kind=NotificationKind.CHANNEL_LIVE, title="Live", message="northernlion is live"
    )
    read = Notification(
        kind=NotificationKind.DOWNLOAD_COMPLETED, title="Done", message="Saved", is_read=True
    )
    await notifications.save(unread)
    await notifications.save(read)

    result = await ListUnreadNotificationsUseCase(notifications=notifications).execute()

    assert result == [unread]


async def test_mark_notification_read():
    notifications = InMemoryNotificationRepository()
    notification = Notification(
        kind=NotificationKind.DOWNLOAD_FAILED, title="Failed", message="Network error"
    )
    await notifications.save(notification)

    await MarkNotificationReadUseCase(notifications=notifications).execute(notification.id)

    remaining_unread = await notifications.list_unread()
    assert remaining_unread == []
