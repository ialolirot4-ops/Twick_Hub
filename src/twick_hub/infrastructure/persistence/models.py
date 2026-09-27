"""ORM tables (Master Plan §14). One table per aggregate the domain
already has a Repository protocol for — ``channels``, ``favorites``,
``playlists``/``playlist_items``, ``scheduled_downloads``,
``notifications``, ``downloads``. §14 also lists ``accounts``,
``platform_accounts``, ``streams``, ``videos``, ``clips``,
``download_segments``, ``download_history``, and ``app_events`` — none of
those have a domain protocol yet to persist through
(``DownloadJob``/``DownloadSegment`` are explicitly transient, per
domain/downloads.py's own module docstring), so no table is created for
them here; see docs/risk-register.md's FASE 8 entry. ``settings`` *is*
here now — FASE 13 added its domain protocol first, per that same entry's
own instruction ("that phase adds the table and migration then").

Value objects (``PlatformRef``, ``Media``, ``Duration``) have no table of
their own — they're flattened into columns on whichever row embeds them,
same as any relational mapping of a value object. See mappers.py for the
domain-entity <-> row conversions.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from twick_hub.infrastructure.persistence.base import Base


class ChannelRow(Base):
    __tablename__ = "channels"

    platform: Mapped[str] = mapped_column(String(16), primary_key=True)
    external_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    username: Mapped[str] = mapped_column(String(256))
    display_name: Mapped[str] = mapped_column(String(256))
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    is_live: Mapped[bool] = mapped_column(Boolean, default=False)
    stream_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    category: Mapped[str | None] = mapped_column(String(256), nullable=True)
    follower_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_verified_or_partner: Mapped[bool] = mapped_column(Boolean, default=False)


class FavoriteRow(Base):
    __tablename__ = "favorites"
    __table_args__ = (
        Index("ix_favorites_channel", "channel_platform", "channel_external_id"),
        Index("ix_favorites_position", "position"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    channel_platform: Mapped[str] = mapped_column(String(16))
    channel_external_id: Mapped[str] = mapped_column(String(128))
    notify_on_live: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_download: Mapped[bool] = mapped_column(Boolean, default=False)
    preferred_quality: Mapped[str | None] = mapped_column(String(32), nullable=True)
    preferred_format: Mapped[str | None] = mapped_column(String(16), nullable=True)
    download_directory: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    added_at: Mapped[datetime] = mapped_column(DateTime)


class PlaylistRow(Base):
    __tablename__ = "playlists"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime)

    items: Mapped[list[PlaylistItemRow]] = relationship(
        back_populates="playlist", cascade="all, delete-orphan", order_by="PlaylistItemRow.position"
    )


class PlaylistItemRow(Base):
    __tablename__ = "playlist_items"
    __table_args__ = (Index("ix_playlist_items_playlist_id", "playlist_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    playlist_id: Mapped[str] = mapped_column(ForeignKey("playlists.id"))
    position: Mapped[int] = mapped_column(Integer)
    added_at: Mapped[datetime] = mapped_column(DateTime)

    media_kind: Mapped[str] = mapped_column(String(16))
    media_platform: Mapped[str] = mapped_column(String(16))
    media_external_id: Mapped[str] = mapped_column(String(128))
    media_title: Mapped[str] = mapped_column(String(512))
    media_channel_platform: Mapped[str | None] = mapped_column(String(16), nullable=True)
    media_channel_external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    media_thumbnail_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    media_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    playlist: Mapped[PlaylistRow] = relationship(back_populates="items")


class ScheduledDownloadRow(Base):
    __tablename__ = "scheduled_downloads"
    __table_args__ = (
        Index("ix_scheduled_downloads_channel", "channel_platform", "channel_external_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    channel_platform: Mapped[str] = mapped_column(String(16))
    channel_external_id: Mapped[str] = mapped_column(String(128))
    trigger: Mapped[str] = mapped_column(String(32))
    quality_preference: Mapped[str] = mapped_column(String(32), default="best")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # FASE 11 — see domain.collections.ScheduledDownload
    run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    weekdays: Mapped[str] = mapped_column(String(16), default="", server_default="")  # "0,2,4"
    window_seconds: Mapped[int] = mapped_column(Integer, default=14400, server_default="14400")
    priority: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    download_directory: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    preferred_format: Mapped[str | None] = mapped_column(String(16), nullable=True)
    next_due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    download_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_outcome: Mapped[str | None] = mapped_column(String(16), nullable=True)


class NotificationRow(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_is_read", "is_read"),
        Index("ix_notifications_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    kind: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(256))
    message: Mapped[str] = mapped_column(String(1024))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime)

    related_media_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    related_media_platform: Mapped[str | None] = mapped_column(String(16), nullable=True)
    related_media_external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    related_media_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    related_media_channel_platform: Mapped[str | None] = mapped_column(String(16), nullable=True)
    related_media_channel_external_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    related_media_thumbnail_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    related_media_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)


class DownloadRow(Base):
    __tablename__ = "downloads"
    __table_args__ = (
        Index("ix_downloads_status", "status"),
        Index("ix_downloads_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)

    media_kind: Mapped[str] = mapped_column(String(16))
    media_platform: Mapped[str] = mapped_column(String(16))
    media_external_id: Mapped[str] = mapped_column(String(128))
    media_title: Mapped[str] = mapped_column(String(512))
    media_channel_platform: Mapped[str | None] = mapped_column(String(16), nullable=True)
    media_channel_external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    media_thumbnail_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    media_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    destination_path: Mapped[str] = mapped_column(String(2048))
    quality_label: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    progress_percent: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2048), nullable=True)


class SettingsRow(Base):
    """One row — see domain/settings.py's module docstring for why this
    table (deferred from FASE 8, see this file's own docstring) exists
    only now, in FASE 13."""

    __tablename__ = "settings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)

    language: Mapped[str] = mapped_column(String(16))
    minimize_to_tray: Mapped[bool] = mapped_column(Boolean)

    default_directory: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    default_quality_preference: Mapped[str] = mapped_column(String(32))
    default_format: Mapped[str | None] = mapped_column(String(16), nullable=True)
    max_concurrent_downloads: Mapped[int] = mapped_column(Integer)
    retry_max_attempts: Mapped[int] = mapped_column(Integer)
    retry_base_delay_seconds: Mapped[float] = mapped_column(Float)
    retry_max_delay_seconds: Mapped[float] = mapped_column(Float)

    notifications_enabled: Mapped[bool] = mapped_column(Boolean)

    theme: Mapped[str] = mapped_column(String(16))

    temp_directory: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    live_monitor_poll_interval_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)


class UpdateAttemptRow(Base):
    """See domain/updates.py's ``UpdateAttempt`` — one row per
    check-download-install cycle (FASE 14)."""

    __tablename__ = "update_attempts"
    __table_args__ = (Index("ix_update_attempts_started_at", "started_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)

    from_version: Mapped[str] = mapped_column(String(32))
    to_version: Mapped[str] = mapped_column(String(32))
    download_url: Mapped[str] = mapped_column(String(2048))
    sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[datetime] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    artifact_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    backup_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2048), nullable=True)


class LegacyMigrationRunRow(Base):
    """See domain/migration.py's ``LegacyMigrationRun`` — one row per
    detect-backup-read-validate-transform-write-verify cycle over a
    TwitchLink 3.5.x ``settings.json`` (FASE 15).

    ``created_*_ids`` are comma-joined uuid hex ids — same convention as
    ``ScheduledDownloadRow.weekdays`` (see mappers.py): ids never contain
    a comma, so a plain split is safe and a dedicated join table would be
    pure overhead for a handful of ids per run. ``warnings`` and
    ``skipped_*`` are newline-joined for the same reason, with any literal
    newline inside one message replaced before joining so splitting back
    on ``"\\n"`` is always unambiguous.
    """

    __tablename__ = "legacy_migration_runs"
    __table_args__ = (Index("ix_legacy_migration_runs_source_sha256", "source_sha256"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)

    source_path: Mapped[str] = mapped_column(String(2048))
    source_sha256: Mapped[str] = mapped_column(String(64))
    backup_path: Mapped[str] = mapped_column(String(2048))
    status: Mapped[str] = mapped_column(String(24))
    started_at: Mapped[datetime] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    settings_migrated: Mapped[bool] = mapped_column(Boolean, default=False)
    previous_settings_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    account_token_migrated: Mapped[bool] = mapped_column(Boolean, default=False)

    created_favorite_ids: Mapped[str] = mapped_column(Text, default="")
    created_scheduled_download_ids: Mapped[str] = mapped_column(Text, default="")
    created_download_ids: Mapped[str] = mapped_column(Text, default="")
    skipped_bookmark_logins: Mapped[str] = mapped_column(Text, default="")
    skipped_scheduled_download_logins: Mapped[str] = mapped_column(Text, default="")
    warnings: Mapped[str] = mapped_column(Text, default="")

    error_message: Mapped[str | None] = mapped_column(String(2048), nullable=True)
