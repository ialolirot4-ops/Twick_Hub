"""Domain entity <-> ORM row conversions. Kept separate from the
repository classes themselves (same split as infrastructure/kick's
mappers.py, AD-28) so persistence-shape decisions live in one place
instead of scattered across every repository's save()/get().

``Media``/``PlatformRef``/``Duration`` are value objects with no table of
their own (models.py's module docstring) — flattened into a handful of
columns wherever they're embedded. The two helpers below
(``_media_columns``/``_media_from_row``) do that flattening once, reused
by every row type that embeds a ``Media`` (playlist items, notifications,
downloads) instead of repeating it three times.
"""

from __future__ import annotations

from twick_hub.domain.collections import Favorite, Playlist, PlaylistItem, ScheduledDownload
from twick_hub.domain.downloads import Download
from twick_hub.domain.enums import (
    DownloadStatus,
    LegacyMigrationStatus,
    MediaKind,
    NotificationKind,
    Platform,
    ScheduleOutcome,
    ScheduleTrigger,
    Theme,
    UpdateStatus,
)
from twick_hub.domain.identity import Channel, User
from twick_hub.domain.migration import LegacyMigrationRun
from twick_hub.domain.notifications import Notification
from twick_hub.domain.settings import Settings
from twick_hub.domain.updates import UpdateAttempt
from twick_hub.domain.value_objects import Duration, Media, PlatformRef
from twick_hub.domain.version import Version
from twick_hub.infrastructure.persistence.models import (
    ChannelRow,
    DownloadRow,
    FavoriteRow,
    LegacyMigrationRunRow,
    NotificationRow,
    PlaylistItemRow,
    PlaylistRow,
    ScheduledDownloadRow,
    SettingsRow,
    UpdateAttemptRow,
)


def _media_columns(media: Media, prefix: str = "media") -> dict[str, object]:
    channel_ref = media.channel_ref
    return {
        f"{prefix}_kind": media.kind.value,
        f"{prefix}_platform": media.ref.platform.value,
        f"{prefix}_external_id": media.ref.external_id,
        f"{prefix}_title": media.title,
        f"{prefix}_channel_platform": channel_ref.platform.value if channel_ref else None,
        f"{prefix}_channel_external_id": channel_ref.external_id if channel_ref else None,
        f"{prefix}_thumbnail_url": media.thumbnail_url,
        f"{prefix}_duration_seconds": media.duration.total_seconds if media.duration else None,
    }


def _media_from_row(row: object, prefix: str = "media") -> Media:
    channel_platform = getattr(row, f"{prefix}_channel_platform")
    channel_external_id = getattr(row, f"{prefix}_channel_external_id")
    duration_seconds = getattr(row, f"{prefix}_duration_seconds")
    return Media(
        kind=MediaKind(getattr(row, f"{prefix}_kind")),
        ref=PlatformRef(
            platform=Platform(getattr(row, f"{prefix}_platform")),
            external_id=getattr(row, f"{prefix}_external_id"),
        ),
        title=getattr(row, f"{prefix}_title"),
        channel_ref=(
            PlatformRef(platform=Platform(channel_platform), external_id=channel_external_id)
            if channel_platform is not None
            else None
        ),
        thumbnail_url=getattr(row, f"{prefix}_thumbnail_url"),
        duration=Duration(total_seconds=duration_seconds) if duration_seconds is not None else None,
    )


# --- channel -------------------------------------------------


def channel_to_row(channel: Channel) -> ChannelRow:
    return ChannelRow(
        platform=channel.ref.platform.value,
        external_id=channel.ref.external_id,
        username=channel.user.username,
        display_name=channel.user.display_name,
        avatar_url=channel.user.avatar_url,
        is_live=channel.is_live,
        stream_title=channel.stream_title,
        category=channel.category,
        follower_count=channel.follower_count,
        is_verified_or_partner=channel.is_verified_or_partner,
    )


def row_to_channel(row: ChannelRow) -> Channel:
    ref = PlatformRef(platform=Platform(row.platform), external_id=row.external_id)
    user = User(
        ref=ref, username=row.username, display_name=row.display_name, avatar_url=row.avatar_url
    )
    return Channel(
        ref=ref,
        user=user,
        is_live=row.is_live,
        stream_title=row.stream_title,
        category=row.category,
        follower_count=row.follower_count,
        is_verified_or_partner=row.is_verified_or_partner,
    )


# --- favorite -------------------------------------------------


def favorite_to_row(favorite: Favorite) -> FavoriteRow:
    return FavoriteRow(
        id=favorite.id,
        channel_platform=favorite.channel_ref.platform.value,
        channel_external_id=favorite.channel_ref.external_id,
        notify_on_live=favorite.notify_on_live,
        auto_download=favorite.auto_download,
        preferred_quality=favorite.preferred_quality,
        preferred_format=favorite.preferred_format,
        download_directory=favorite.download_directory,
        position=favorite.position,
        added_at=favorite.added_at,
    )


def row_to_favorite(row: FavoriteRow) -> Favorite:
    channel_ref = PlatformRef(
        platform=Platform(row.channel_platform), external_id=row.channel_external_id
    )
    return Favorite(
        id=row.id,
        channel_ref=channel_ref,
        notify_on_live=row.notify_on_live,
        auto_download=row.auto_download,
        preferred_quality=row.preferred_quality,
        preferred_format=row.preferred_format,
        download_directory=row.download_directory,
        position=row.position,
        added_at=row.added_at,
    )


# --- playlist -------------------------------------------------


def playlist_to_row(playlist: Playlist) -> PlaylistRow:
    row = PlaylistRow(id=playlist.id, name=playlist.name, created_at=playlist.created_at)
    row.items = [_playlist_item_to_row(item, playlist.id) for item in playlist.items]
    return row


def _playlist_item_to_row(item: PlaylistItem, playlist_id: str) -> PlaylistItemRow:
    return PlaylistItemRow(
        id=item.id,
        playlist_id=playlist_id,
        position=item.position,
        added_at=item.added_at,
        **_media_columns(item.media),
    )


def row_to_playlist(row: PlaylistRow) -> Playlist:
    items = tuple(
        PlaylistItem(
            id=item.id, media=_media_from_row(item), position=item.position, added_at=item.added_at
        )
        for item in row.items
    )
    return Playlist(id=row.id, name=row.name, created_at=row.created_at, items=items)


# --- scheduled download -------------------------------------------------


def scheduled_download_to_row(scheduled: ScheduledDownload) -> ScheduledDownloadRow:
    return ScheduledDownloadRow(
        id=scheduled.id,
        channel_platform=scheduled.channel_ref.platform.value,
        channel_external_id=scheduled.channel_ref.external_id,
        trigger=scheduled.trigger.value,
        quality_preference=scheduled.quality_preference,
        is_active=scheduled.is_active,
        created_at=scheduled.created_at,
        last_triggered_at=scheduled.last_triggered_at,
        run_at=scheduled.run_at,
        weekdays=",".join(str(day) for day in scheduled.weekdays),
        window_seconds=scheduled.window_seconds,
        priority=scheduled.priority,
        max_attempts=scheduled.max_attempts,
        download_directory=scheduled.download_directory,
        preferred_format=scheduled.preferred_format,
        next_due_at=scheduled.next_due_at,
        attempts=scheduled.attempts,
        download_id=scheduled.download_id,
        last_outcome=scheduled.last_outcome.value if scheduled.last_outcome else None,
    )


def row_to_scheduled_download(row: ScheduledDownloadRow) -> ScheduledDownload:
    channel_ref = PlatformRef(
        platform=Platform(row.channel_platform), external_id=row.channel_external_id
    )
    return ScheduledDownload(
        id=row.id,
        channel_ref=channel_ref,
        trigger=ScheduleTrigger(row.trigger),
        quality_preference=row.quality_preference,
        is_active=row.is_active,
        created_at=row.created_at,
        last_triggered_at=row.last_triggered_at,
        run_at=row.run_at,
        weekdays=tuple(int(day) for day in row.weekdays.split(",") if day),
        window_seconds=row.window_seconds,
        priority=row.priority,
        max_attempts=row.max_attempts,
        download_directory=row.download_directory,
        preferred_format=row.preferred_format,
        next_due_at=row.next_due_at,
        attempts=row.attempts,
        download_id=row.download_id,
        last_outcome=ScheduleOutcome(row.last_outcome) if row.last_outcome else None,
    )


# --- notification -------------------------------------------------


def notification_to_row(notification: Notification) -> NotificationRow:
    media_columns = (
        _media_columns(notification.related_media, prefix="related_media")
        if notification.related_media is not None
        else dict.fromkeys(
            (
                "related_media_kind",
                "related_media_platform",
                "related_media_external_id",
                "related_media_title",
                "related_media_channel_platform",
                "related_media_channel_external_id",
                "related_media_thumbnail_url",
                "related_media_duration_seconds",
            )
        )
    )
    return NotificationRow(
        id=notification.id,
        kind=notification.kind.value,
        title=notification.title,
        message=notification.message,
        is_read=notification.is_read,
        created_at=notification.created_at,
        **media_columns,
    )


def row_to_notification(row: NotificationRow) -> Notification:
    related_media = (
        _media_from_row(row, prefix="related_media") if row.related_media_kind is not None else None
    )
    return Notification(
        id=row.id,
        kind=NotificationKind(row.kind),
        title=row.title,
        message=row.message,
        related_media=related_media,
        is_read=row.is_read,
        created_at=row.created_at,
    )


# --- download -------------------------------------------------


def download_to_row(download: Download) -> DownloadRow:
    return DownloadRow(
        id=download.id,
        destination_path=download.destination_path,
        quality_label=download.quality_label,
        status=download.status.value,
        progress_percent=download.progress_percent,
        created_at=download.created_at,
        completed_at=download.completed_at,
        file_size_bytes=download.file_size_bytes,
        error_message=download.error_message,
        **_media_columns(download.media),
    )


def row_to_download(row: DownloadRow) -> Download:
    return Download(
        id=row.id,
        media=_media_from_row(row),
        destination_path=row.destination_path,
        quality_label=row.quality_label,
        status=DownloadStatus(row.status),
        progress_percent=row.progress_percent,
        created_at=row.created_at,
        completed_at=row.completed_at,
        file_size_bytes=row.file_size_bytes,
        error_message=row.error_message,
    )


def settings_to_row(settings: Settings) -> SettingsRow:
    return SettingsRow(
        id=settings.id,
        language=settings.language,
        minimize_to_tray=settings.minimize_to_tray,
        default_directory=settings.default_directory,
        default_quality_preference=settings.default_quality_preference,
        default_format=settings.default_format,
        max_concurrent_downloads=settings.max_concurrent_downloads,
        retry_max_attempts=settings.retry_max_attempts,
        retry_base_delay_seconds=settings.retry_base_delay_seconds,
        retry_max_delay_seconds=settings.retry_max_delay_seconds,
        notifications_enabled=settings.notifications_enabled,
        theme=settings.theme.value,
        temp_directory=settings.temp_directory,
        live_monitor_poll_interval_seconds=settings.live_monitor_poll_interval_seconds,
    )


def row_to_settings(row: SettingsRow) -> Settings:
    return Settings(
        id=row.id,
        language=row.language,
        minimize_to_tray=row.minimize_to_tray,
        default_directory=row.default_directory,
        default_quality_preference=row.default_quality_preference,
        default_format=row.default_format,
        max_concurrent_downloads=row.max_concurrent_downloads,
        retry_max_attempts=row.retry_max_attempts,
        retry_base_delay_seconds=row.retry_base_delay_seconds,
        retry_max_delay_seconds=row.retry_max_delay_seconds,
        notifications_enabled=row.notifications_enabled,
        theme=Theme(row.theme),
        temp_directory=row.temp_directory,
        live_monitor_poll_interval_seconds=row.live_monitor_poll_interval_seconds,
    )


def update_attempt_to_row(attempt: UpdateAttempt) -> UpdateAttemptRow:
    return UpdateAttemptRow(
        id=attempt.id,
        from_version=str(attempt.from_version),
        to_version=str(attempt.to_version),
        download_url=attempt.download_url,
        sha256=attempt.sha256,
        status=attempt.status.value,
        started_at=attempt.started_at,
        finished_at=attempt.finished_at,
        artifact_path=attempt.artifact_path,
        backup_path=attempt.backup_path,
        error_message=attempt.error_message,
    )


def row_to_update_attempt(row: UpdateAttemptRow) -> UpdateAttempt:
    return UpdateAttempt(
        id=row.id,
        from_version=Version.parse(row.from_version),
        to_version=Version.parse(row.to_version),
        download_url=row.download_url,
        sha256=row.sha256,
        status=UpdateStatus(row.status),
        started_at=row.started_at,
        finished_at=row.finished_at,
        artifact_path=row.artifact_path,
        backup_path=row.backup_path,
        error_message=row.error_message,
    )


# --- legacy migration run -------------------------------------------------

_LEGACY_IDS_SEP = ","
_LEGACY_LINES_SEP = "\n"


def _join_ids(ids: tuple[str, ...]) -> str:
    return _LEGACY_IDS_SEP.join(ids)


def _split_ids(value: str) -> tuple[str, ...]:
    return tuple(item for item in value.split(_LEGACY_IDS_SEP) if item)


def _join_lines(lines: tuple[str, ...]) -> str:
    return _LEGACY_LINES_SEP.join(line.replace(_LEGACY_LINES_SEP, " ") for line in lines)


def _split_lines(value: str) -> tuple[str, ...]:
    return tuple(line for line in value.split(_LEGACY_LINES_SEP) if line)


def legacy_migration_run_to_row(run: LegacyMigrationRun) -> LegacyMigrationRunRow:
    return LegacyMigrationRunRow(
        id=run.id,
        source_path=run.source_path,
        source_sha256=run.source_sha256,
        backup_path=run.backup_path,
        status=run.status.value,
        started_at=run.started_at,
        finished_at=run.finished_at,
        settings_migrated=run.settings_migrated,
        previous_settings_json=run.previous_settings_json,
        account_token_migrated=run.account_token_migrated,
        created_favorite_ids=_join_ids(run.created_favorite_ids),
        created_scheduled_download_ids=_join_ids(run.created_scheduled_download_ids),
        created_download_ids=_join_ids(run.created_download_ids),
        skipped_bookmark_logins=_join_lines(run.skipped_bookmark_logins),
        skipped_scheduled_download_logins=_join_lines(run.skipped_scheduled_download_logins),
        warnings=_join_lines(run.warnings),
        error_message=run.error_message,
    )


def row_to_legacy_migration_run(row: LegacyMigrationRunRow) -> LegacyMigrationRun:
    return LegacyMigrationRun(
        id=row.id,
        source_path=row.source_path,
        source_sha256=row.source_sha256,
        backup_path=row.backup_path,
        status=LegacyMigrationStatus(row.status),
        started_at=row.started_at,
        finished_at=row.finished_at,
        settings_migrated=row.settings_migrated,
        previous_settings_json=row.previous_settings_json,
        account_token_migrated=row.account_token_migrated,
        created_favorite_ids=_split_ids(row.created_favorite_ids),
        created_scheduled_download_ids=_split_ids(row.created_scheduled_download_ids),
        created_download_ids=_split_ids(row.created_download_ids),
        skipped_bookmark_logins=_split_lines(row.skipped_bookmark_logins),
        skipped_scheduled_download_logins=_split_lines(row.skipped_scheduled_download_logins),
        warnings=_split_lines(row.warnings),
        error_message=row.error_message,
    )
