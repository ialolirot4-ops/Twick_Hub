"""User-collection entities: things the person curates themselves —
favorites, playlists, and scheduled downloads.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from uuid import uuid4

from twitchlink_next.domain.enums import ScheduleTrigger
from twitchlink_next.domain.value_objects import Media, PlatformRef


@dataclass(frozen=True, slots=True)
class Favorite:
    channel_ref: PlatformRef
    notify_on_live: bool = True
    auto_download: bool = False
    id: str = field(default_factory=lambda: uuid4().hex)
    added_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True, slots=True)
class PlaylistItem:
    media: Media
    position: int
    id: str = field(default_factory=lambda: uuid4().hex)
    added_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True, slots=True)
class Playlist:
    name: str
    items: tuple[PlaylistItem, ...] = ()
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: datetime = field(default_factory=datetime.now)

    def with_item_added(self, media: Media) -> Playlist:
        """Returns a new Playlist with ``media`` appended at the end.

        Entities here are immutable (see identity.py's module docstring),
        so "adding an item" is a pure function returning a new value
        rather than mutating ``items`` in place.
        """
        new_item = PlaylistItem(media=media, position=len(self.items))
        return replace(self, items=(*self.items, new_item))


@dataclass(frozen=True, slots=True)
class ScheduledDownload:
    channel_ref: PlatformRef
    trigger: ScheduleTrigger
    quality_preference: str = "best"
    is_active: bool = True
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: datetime = field(default_factory=datetime.now)
    last_triggered_at: datetime | None = None
