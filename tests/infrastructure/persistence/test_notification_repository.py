from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import sessionmaker

from twick_hub.domain.enums import MediaKind, NotificationKind, Platform
from twick_hub.domain.notifications import Notification
from twick_hub.domain.value_objects import Media, PlatformRef
from twick_hub.infrastructure.persistence.notification_repository import SqlNotificationRepository


def _notification(
    created_at: datetime | None = None, related_media: Media | None = None
) -> Notification:
    return Notification(
        kind=NotificationKind.CHANNEL_LIVE,
        title="Channel is live",
        message="northernlion just went live",
        related_media=related_media,
        created_at=created_at or datetime.now(),
    )


async def test_list_unread_excludes_read_notifications(session_factory: sessionmaker):
    repo = SqlNotificationRepository(session_factory)
    unread = _notification()
    read = _notification()
    await repo.save(unread)
    await repo.save(read)
    await repo.mark_read(read.id)

    result = await repo.list_unread()

    assert [n.id for n in result] == [unread.id]


async def test_save_round_trips_without_related_media(session_factory: sessionmaker):
    repo = SqlNotificationRepository(session_factory)
    notification = _notification()

    await repo.save(notification)
    result = await repo.list_unread()

    assert result == [notification]
    assert result[0].related_media is None


async def test_save_round_trips_with_related_media(session_factory: sessionmaker):
    repo = SqlNotificationRepository(session_factory)
    media = Media(
        kind=MediaKind.STREAM,
        ref=PlatformRef(platform=Platform.TWITCH, external_id="s1"),
        title="Live!",
    )
    notification = _notification(related_media=media)

    await repo.save(notification)
    result = await repo.list_unread()

    assert result[0].related_media == media


async def test_mark_read_of_unknown_id_does_not_raise(session_factory: sessionmaker):
    repo = SqlNotificationRepository(session_factory)
    await repo.mark_read("does-not-exist")


async def test_list_unread_orders_most_recent_first(session_factory: sessionmaker):
    repo = SqlNotificationRepository(session_factory)
    base = datetime(2026, 1, 1)
    older = _notification(base)
    newer = _notification(base + timedelta(hours=1))

    await repo.save(older)
    await repo.save(newer)

    result = await repo.list_unread()
    assert [n.id for n in result] == [newer.id, older.id]


async def test_list_unread_respects_limit_and_offset(session_factory: sessionmaker):
    repo = SqlNotificationRepository(session_factory)
    base = datetime(2026, 1, 1)
    notifications = [_notification(base + timedelta(minutes=i)) for i in range(5)]
    for notification in notifications:
        await repo.save(notification)

    page = await repo.list_unread(limit=2, offset=1)

    # newest-first: [n4, n3, n2, n1, n0] -> offset 1, limit 2 -> [n3, n2]
    assert [n.id for n in page] == [notifications[3].id, notifications[2].id]
