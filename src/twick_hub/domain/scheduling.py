"""The rules Master Plan §20/§48 asks to keep separate: ``Favorite`` (who
the user follows), ``NotificationRule`` (tell me when they go live),
``AutoDownloadRule`` (record them when they go live) and
``ScheduledDownload`` (a time- or event-based one-off / recurring
recording, in collections.py).

The first three used to be one bag of flags on ``Favorite``. They stay
*stored* there (one row, one place to edit — nothing new to migrate), but
every decision is made against these separate types, so a consumer that
only cares about notifications never has to know auto-download exists,
and vice versa.
"""

from __future__ import annotations

from dataclasses import dataclass

from twick_hub.domain.collections import Favorite
from twick_hub.domain.value_objects import PlatformRef


@dataclass(frozen=True, slots=True)
class NotificationRule:
    channel_ref: PlatformRef
    enabled: bool

    @classmethod
    def from_favorite(cls, favorite: Favorite) -> NotificationRule:
        return cls(channel_ref=favorite.channel_ref, enabled=favorite.notify_on_live)


@dataclass(frozen=True, slots=True)
class AutoDownloadRule:
    """Record this channel every time it goes live. ``priority`` is the
    favorite's own ``position`` — the user's ordering *is* their ranking,
    so the first favorite gets a download worker first (lower runs first,
    same scale as ``ScheduledDownload.priority``)."""

    channel_ref: PlatformRef
    enabled: bool
    quality: str = "best"
    file_format: str | None = None
    directory: str | None = None
    priority: int = 0

    @classmethod
    def from_favorite(cls, favorite: Favorite) -> AutoDownloadRule:
        return cls(
            channel_ref=favorite.channel_ref,
            enabled=favorite.auto_download,
            quality=favorite.preferred_quality or "best",
            file_format=favorite.preferred_format,
            directory=favorite.download_directory,
            priority=favorite.position,
        )
