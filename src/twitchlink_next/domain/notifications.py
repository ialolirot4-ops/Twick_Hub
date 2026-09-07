"""Notification entity."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from twitchlink_next.domain.enums import NotificationKind
from twitchlink_next.domain.value_objects import Media


@dataclass(frozen=True, slots=True)
class Notification:
    kind: NotificationKind
    title: str
    message: str
    related_media: Media | None = None
    is_read: bool = False
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: datetime = field(default_factory=datetime.now)
