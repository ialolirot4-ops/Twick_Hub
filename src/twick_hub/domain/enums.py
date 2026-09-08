"""Domain enums.

Pure Python (``enum.Enum``/``StrEnum``) — no PySide6, no SQLAlchemy, no
framework of any kind. Master Plan §37: "Domain no importa PySide6."
"""

from __future__ import annotations

from enum import StrEnum


class Platform(StrEnum):
    """The only two platforms this project supports (Master Plan §1)."""

    TWITCH = "twitch"
    KICK = "kick"


class MediaKind(StrEnum):
    """What kind of content a :class:`~twick_hub.domain.value_objects.Media`
    reference points at."""

    STREAM = "stream"
    VIDEO = "video"
    CLIP = "clip"


class DownloadStatus(StrEnum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SegmentStatus(StrEnum):
    PENDING = "pending"
    DOWNLOADED = "downloaded"
    FAILED = "failed"


class ScheduleTrigger(StrEnum):
    """When a :class:`~twick_hub.domain.collections.ScheduledDownload`
    fires. ON_NEXT_LIVE covers the common "auto-download this channel's next
    stream" case already present in TwitchLink 3.5.5
    (docs/functional-baseline.md); RECURRING is new."""

    ON_NEXT_LIVE = "on_next_live"
    RECURRING = "recurring"


class NotificationKind(StrEnum):
    CHANNEL_LIVE = "channel_live"
    DOWNLOAD_COMPLETED = "download_completed"
    DOWNLOAD_FAILED = "download_failed"
    SCHEDULED_DOWNLOAD_TRIGGERED = "scheduled_download_triggered"
