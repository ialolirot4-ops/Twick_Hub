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
    """Master Plan §44 (FASE 7) names these eight states exactly.
    ``PENDING`` (FASE 3's original name) is renamed to ``QUEUED``, and
    ``PREPARING``/``PROCESSING`` are new — see
    docs/architecture-decisions.md's FASE 7 entry for why this rename
    happened retroactively instead of adding new states under the old
    name."""

    QUEUED = "queued"
    PREPARING = "preparing"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class SegmentStatus(StrEnum):
    PENDING = "pending"
    DOWNLOADED = "downloaded"
    FAILED = "failed"


class ScheduleTrigger(StrEnum):
    """When a :class:`~twick_hub.domain.collections.ScheduledDownload`
    fires (FASE 11 gives each value its meaning — FASE 3 only named them):

    - ``ON_NEXT_LIVE``: the channel's next go-live, once, then it is done.
    - ``RECURRING``: *every* go-live, until the user disables it. This is
      TwitchLink 3.5.5's scheduled-download preset exactly (source:
      ``Download/ScheduledDownloadManager.py`` — it keeps recording each
      time the channel comes online), independent of favorites.
    - ``AT_TIME``: at a date/time (``run_at``), optionally repeating weekly
      (``weekdays``); the channel is recorded if it is live inside the
      ``window_seconds`` that follow. New in Twick Hub (Master Plan §20).
    """

    ON_NEXT_LIVE = "on_next_live"
    RECURRING = "recurring"
    AT_TIME = "at_time"


class NotificationKind(StrEnum):
    CHANNEL_LIVE = "channel_live"
    DOWNLOAD_COMPLETED = "download_completed"
    DOWNLOAD_FAILED = "download_failed"
    SCHEDULED_DOWNLOAD_TRIGGERED = "scheduled_download_triggered"


class ScheduleOutcome(StrEnum):
    """How a scheduled download's most recent run ended."""

    COMPLETED = "completed"
    MISSED = "missed"  # the window closed without the channel ever being live
    FAILED = "failed"  # every attempt failed
    CANCELLED = "cancelled"


class SchedulePhase(StrEnum):
    """Where a scheduled download is *right now* — always derived, never
    stored, so it can't drift from ``next_due_at``/``download_id``."""

    DISABLED = "disabled"
    SCHEDULED = "scheduled"  # AT_TIME, due time still ahead
    WAITING_LIVE = "waiting_live"  # armed: record as soon as the channel is live
    RUNNING = "running"  # a recording is in progress
    EXPIRED = "expired"  # AT_TIME, window closed without a recording


class Theme(StrEnum):
    """Appearance setting (FASE 13, Master Plan §50). ``SYSTEM`` follows the
    OS's own light/dark setting rather than fixing one — the same "system
    default" pattern the Settings page mock already uses for time zone."""

    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


class LegacyMigrationStatus(StrEnum):
    """Lifecycle of one :class:`~twick_hub.domain.migration.LegacyMigrationRun`
    (FASE 15, Master Plan §52). Mirrors ``UpdateStatus``'s "an entity is a
    value with an id and a status" shape (FASE 14) — a migration run is
    inspectable after the fact, possibly across a restart, the same reason
    ``UpdateAttempt`` is persisted rather than kept in memory only.

    There is no ``PARTIALLY_COMPLETED``: ``COMPLETED_WITH_WARNINGS`` is
    that state's honest name — every section the flow could safely
    attempt did run, but at least one *item* inside a section (a bookmark
    login that doesn't resolve to a channel, say) was individually
    skipped and is listed in ``LegacyMigrationRun.warnings`` rather than
    aborting the whole run. Master Plan §0.7: "no afirmar PASS sin
    evidencia" applies at the item level too — a skipped item is recorded
    as skipped, never silently dropped or claimed migrated.
    """

    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class UpdateStatus(StrEnum):
    """Lifecycle of one ``UpdateAttempt`` (FASE 14, Master Plan §51)."""

    CHECKING = "checking"
    AVAILABLE = "available"  # a newer version exists; nothing downloaded yet
    DOWNLOADING = "downloading"
    VERIFYING = "verifying"  # checksum/signature check of the downloaded artifact
    READY_TO_INSTALL = "ready_to_install"
    INSTALLING = "installing"
    INSTALLED = "installed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
