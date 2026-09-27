"""Pure legacy-snapshot -> Twick Hub domain mappings — Master Plan §52
(FASE 15)'s "transform" step.

No I/O, no repository calls, no network lookups: every function here
takes an already-read
:class:`~twick_hub.infrastructure.migration.legacy_reader.LegacyPreferencesSnapshot`
(or a piece of one) and returns a Twick Hub domain value, or plain data a
caller can use to obtain one (a bookmark login still needs an online
channel lookup before it can become a ``Favorite`` — that lookup, and
every write, is application/migration.py's job, not this module's).

IDs are derived deterministically (uuid5, never uuid4) from stable
identifying fields in the legacy data — the only thing that makes
re-running the migrator against the same legacy file idempotent at the
row level (domain/migration.py's module docstring covers the run-level
half of idempotency; this is the item-level half): the same legacy
scheduled-download preset or history entry always produces the same
Twick Hub id, so ``repository.save()``'s upsert-by-id behaviour is a
true no-op on a second run instead of creating a duplicate row.
"""

from __future__ import annotations

from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from twick_hub.domain.collections import ScheduledDownload
from twick_hub.domain.downloads import Download
from twick_hub.domain.enums import DownloadStatus, MediaKind, Platform, ScheduleTrigger, Theme
from twick_hub.domain.value_objects import Duration, Media, PlatformRef
from twick_hub.infrastructure.migration.legacy_reader import (
    LegacyDownloadHistoryEntry,
    LegacyPreferencesSnapshot,
    LegacyScheduledDownloadPreset,
)

_THEME_BY_LEGACY_MODE = {"": Theme.SYSTEM, "light": Theme.LIGHT, "dark": Theme.DARK}

_STATUS_BY_LEGACY_RESULT: dict[str, DownloadStatus] = {
    "download-complete": DownloadStatus.COMPLETED,
    "download-stopped": DownloadStatus.CANCELLED,
    "download-canceled": DownloadStatus.CANCELLED,
    "download-aborted": DownloadStatus.FAILED,
    # A raw, un-healed "downloading" only ever means the legacy process
    # was killed mid-write — TwitchLink's own DownloadHistory.__setup__
    # heals exactly this case into "aborted"/"unexpected-error" the next
    # time it loads its own file. Ported as behavior (Master Plan §0.9),
    # not re-derived.
    "downloading": DownloadStatus.FAILED,
}

_MEDIA_KIND_BY_NAME = {"stream": MediaKind.STREAM, "video": MediaKind.VIDEO, "clip": MediaKind.CLIP}


def deterministic_id(kind: str, *parts: str) -> str:
    """A uuid5, not uuid4 — see this module's docstring. ``kind`` scopes
    the namespace so a stream and a scheduled-download preset that
    happen to share a raw identifying string never collide."""
    name = "twick-hub-legacy-migration:" + ":".join((kind, *parts))
    return uuid5(NAMESPACE_URL, name).hex


# --- settings -------------------------------------------------


def settings_overrides_from_legacy(snapshot: LegacyPreferencesSnapshot) -> dict[str, object]:
    """Fields to apply on top of the *existing* ``Settings`` row via
    ``existing.updated(**overrides)`` — never a fresh ``Settings()``, so
    any field Twick Hub has and legacy never did (e.g.
    ``live_monitor_poll_interval_seconds``) is left exactly as the user
    already had it. Only fields with an unambiguous, direct legacy
    source are included here at all; see docs/architecture-decisions.md's
    FASE 15 entry for the fields deliberately left out (per-content-type
    directories, filename templates, timezone, quality preference —
    none of them have a one-field destination in Twick Hub today).
    """
    overrides: dict[str, object] = {}

    general = snapshot.general
    if general.use_system_tray is not None:
        overrides["minimize_to_tray"] = bool(general.use_system_tray)
    if general.notify is not None:
        overrides["notifications_enabled"] = bool(general.notify)

    if snapshot.advanced.theme_mode is not None:
        theme = _THEME_BY_LEGACY_MODE.get(snapshot.advanced.theme_mode)
        if theme is not None:
            overrides["theme"] = theme

    if snapshot.localization.translation_pack_id:
        overrides["language"] = snapshot.localization.translation_pack_id

    if snapshot.download.download_speed is not None:
        overrides["max_concurrent_downloads"] = max(1, int(snapshot.download.download_speed))

    # StreamHistory is the most representative of the five per-content-type
    # option-history buckets legacy kept (Video/Clip/Thumbnail/Scheduled
    # each had their own directory/format) — Settings has one global
    # default_directory/default_format, so this is a deliberate, lossy
    # collapse, not an oversight. See docs/architecture-decisions.md.
    stream_options = snapshot.download.option_history.get("StreamHistory")
    if stream_options is not None:
        if stream_options.directory:
            overrides["default_directory"] = stream_options.directory
        if stream_options.file_format:
            overrides["default_format"] = stream_options.file_format

    return overrides


# --- scheduled downloads -------------------------------------------------


def scheduled_download_from_preset(
    preset: LegacyScheduledDownloadPreset, *, channel_ref: PlatformRef, master_enabled: bool
) -> ScheduledDownload:
    """One legacy ``ScheduledDownloadPreset`` -> one ``RECURRING``
    ``ScheduledDownload`` (``ScheduleTrigger.RECURRING``'s own docstring
    names this exact legacy source). ``master_enabled`` is legacy's
    single global on/off switch for the whole scheduler
    (``ScheduledDownloads._enabled``) — Twick Hub has no equivalent
    global switch, only per-item ``is_active``, so a disabled global
    switch is honored by folding it into every migrated item's
    ``is_active`` instead of inventing a new Settings field for it.
    """
    return ScheduledDownload(
        id=deterministic_id("scheduled_download", channel_ref.external_id),
        channel_ref=channel_ref,
        trigger=ScheduleTrigger.RECURRING,
        quality_preference=preset.quality_preference,
        is_active=preset.enabled and master_enabled,
        download_directory=preset.directory,
        preferred_format=preset.file_format,
    )


# --- download history -------------------------------------------------


_FALLBACK_DESTINATION = "(legacy record incomplete — destination unknown)"
_FALLBACK_QUALITY_LABEL = "unknown"  # legacy only stored an index into a
# per-stream quality list that was never itself persisted — nothing to
# recover the real label from. Documented as a gap, not a bug.


def download_from_history_entry(
    entry: LegacyDownloadHistoryEntry, *, channel_ref: PlatformRef | None
) -> Download:
    media = Media(
        kind=_MEDIA_KIND_BY_NAME[entry.media_kind],
        ref=PlatformRef(platform=Platform.TWITCH, external_id=entry.content_id),
        title=entry.title,
        channel_ref=channel_ref,
        duration=Duration(total_seconds=entry.duration_seconds)
        if entry.duration_seconds is not None
        else None,
    )

    if entry.directory and entry.file_name and entry.file_format:
        destination_path = f"{entry.directory.rstrip('/')}/{entry.file_name}.{entry.file_format}"
    else:
        destination_path = entry.directory or _FALLBACK_DESTINATION

    status = (
        _STATUS_BY_LEGACY_RESULT.get(entry.result, DownloadStatus.FAILED)
        if entry.result is not None
        else DownloadStatus.FAILED
    )
    error_message = entry.error
    if error_message is None and entry.result == "downloading":
        error_message = "unexpected-error (interrupted; inherited from legacy history)"
    elif error_message is None and entry.result is None:
        error_message = "legacy history entry had no recorded result"

    progress_percent = 100.0 if status is DownloadStatus.COMPLETED else 0.0
    if status is not DownloadStatus.COMPLETED and entry.progress_ratio is not None:
        progress_percent = round(entry.progress_ratio * 100.0, 2)

    created_at = entry.started_at or entry.completed_at or datetime(1970, 1, 1)

    return Download(
        id=deterministic_id(
            "download_history", entry.media_kind, entry.content_id, created_at.isoformat()
        ),
        media=media,
        destination_path=destination_path,
        quality_label=_FALLBACK_QUALITY_LABEL,
        status=status,
        progress_percent=progress_percent,
        created_at=created_at,
        completed_at=entry.completed_at,
        file_size_bytes=entry.byte_size,
        error_message=error_message,
    )
