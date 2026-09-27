"""Reads and validates a TwitchLink 3.5.x ``settings.json`` — Master Plan
§52 (FASE 15)'s "read" and "validate" steps.

Turns the tagged JSON (via ``legacy_codec.decode``) into a typed, mostly-
optional :class:`LegacyPreferencesSnapshot`. Every field the legacy
``Preferences`` object could have written is optional here on purpose —
an older/newer legacy version, a fresh install that never finished setup,
or a hand-edited file can all be missing sections a fully-populated file
would have; "validate" rejects a file that doesn't look like a
Preferences dump *at all*, not one that is merely incomplete.

Anything below the top level that fails to parse in a *locally
recoverable* way (one malformed download-history entry among a hundred
good ones, say) is skipped and recorded in ``snapshot.warnings`` rather
than aborting the whole read — Master Plan §0.7: "si una validación no
pudo ejecutarse, debe aparecer literalmente como PENDING o BLOCKED;
nunca como PASS implícito." A structurally-unreadable top level (not
even a JSON object, or none of the known Preferences sections present at
all) is the one case that raises, since there is nothing safe to return.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from twick_hub.infrastructure.migration.legacy_codec import LegacyCodecError, LegacyObject, decode

# Preferences.getSaveData()'s exact key set (excludes "logger", the one
# key that method itself filters out).
_KNOWN_SECTIONS = frozenset(
    {
        "setup",
        "account",
        "general",
        "templates",
        "advanced",
        "localization",
        "temp",
        "download",
        "scheduledDownloads",
    }
)

# ScheduledDownloadPreset.AVAILABLE_QUALITY.getList()'s exact order —
# preferredQualityIndex indexes into this fixed tuple in the legacy
# source, not a stored value. Ported verbatim (Master Plan §0.9: legacy
# behavior, not architecture) rather than re-derived.
_LEGACY_QUALITY_INDEX = ("best", "1080p", "720p", "480p", "360p", "160p", "worst", "audio-only")

_RESULT_STATUS = frozenset(
    {
        "download-complete",
        "download-stopped",
        "download-canceled",
        "download-aborted",
        "downloading",
    }
)


class LegacyValidationError(Exception):
    """The file parsed as JSON and decoded without error, but its shape
    doesn't resemble a TwitchLink Preferences dump — e.g. the top level
    isn't an object, or none of the known Preferences sections are
    present. Distinct from ``LegacyCodecError`` (legacy_codec.py): that
    is "the tagged-string envelope itself is malformed"; this is "the
    envelope is fine, but the contents aren't a Preferences dump."
    """


def sha256_of(raw_bytes: bytes) -> str:
    """The migration idempotency key (domain/migration.py's module
    docstring) — lowercase hex, matching ``UpdateInfo.sha256``'s own
    format for the same reason: a stable, comparable fingerprint of
    exactly the bytes on disk."""
    return hashlib.sha256(raw_bytes).hexdigest()


# --- typed snapshot -------------------------------------------------


@dataclass(frozen=True, slots=True)
class LegacyAccountSecret:
    """Never logged, never put in a report string, never written to
    anything but the OS credential store (Master Plan §52: "Secretos:
    credential store, nunca JSON/SQLite") — held only transiently in
    memory between "read" and "write". ``username``/``platform_user_id``
    are NOT secret (Twitch logins are public) and exist only so a
    caller can label the credential-store entry; they are never
    persisted as a row anywhere (see docs/architecture-decisions.md's
    FASE 15 entry — Twick Hub has no ``PlatformAccount`` table at all,
    by design, since FASE 8).
    """

    token: str
    platform_user_id: str | None = None
    username: str | None = None
    expiration: datetime | None = None


@dataclass(frozen=True, slots=True)
class LegacyGeneralSection:
    notify: bool | None = None
    use_system_tray: bool | None = None
    bookmarks: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LegacyAdvancedSection:
    theme_mode: str | None = None  # "" (auto) / "light" / "dark"


@dataclass(frozen=True, slots=True)
class LegacyLocalizationSection:
    translation_pack_id: str | None = None


@dataclass(frozen=True, slots=True)
class LegacyDownloadOptionHistoryEntry:
    directory: str | None = None
    file_format: str | None = None


@dataclass(frozen=True, slots=True)
class LegacyDownloadSection:
    download_speed: int | None = None  # FileDownloadManager pool size
    option_history: dict[str, LegacyDownloadOptionHistoryEntry] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LegacyScheduledDownloadPreset:
    channel_login: str
    quality_preference: str  # already resolved via _LEGACY_QUALITY_INDEX
    enabled: bool
    file_format: str | None = None
    directory: str | None = None


@dataclass(frozen=True, slots=True)
class LegacyScheduledDownloadsSection:
    enabled: bool = False
    presets: tuple[LegacyScheduledDownloadPreset, ...] = ()


@dataclass(frozen=True, slots=True)
class LegacyDownloadHistoryEntry:
    media_kind: str  # "stream" / "video" / "clip"
    content_id: str
    title: str
    channel_external_id: str | None
    duration_seconds: int | None
    directory: str | None
    file_name: str | None
    file_format: str | None
    started_at: datetime | None
    completed_at: datetime | None
    result: str | None
    error: str | None
    byte_size: int | None
    progress_ratio: float | None  # milliseconds / totalMilliseconds, when known


@dataclass(frozen=True, slots=True)
class LegacyPreferencesSnapshot:
    account_secret: LegacyAccountSecret | None = None
    general: LegacyGeneralSection = field(default_factory=LegacyGeneralSection)
    advanced: LegacyAdvancedSection = field(default_factory=LegacyAdvancedSection)
    localization: LegacyLocalizationSection = field(default_factory=LegacyLocalizationSection)
    download: LegacyDownloadSection = field(default_factory=LegacyDownloadSection)
    scheduled_downloads: LegacyScheduledDownloadsSection = field(
        default_factory=LegacyScheduledDownloadsSection
    )
    download_history: tuple[LegacyDownloadHistoryEntry, ...] = ()
    warnings: tuple[str, ...] = ()


# --- top level -------------------------------------------------


def read_legacy_file(path: Path) -> bytes:
    """Reads the raw bytes only — no parsing. Split out from
    :func:`parse_snapshot` so a caller (the application service) can
    hash the exact same bytes it's about to parse, and so tests can feed
    :func:`parse_snapshot` bytes directly without touching a filesystem.
    """
    return path.read_bytes()


def parse_snapshot(raw_bytes: bytes) -> LegacyPreferencesSnapshot:
    """FASE 15's "read" + "validate" steps combined. Raises
    :class:`LegacyCodecError` if the bytes aren't valid JSON or don't
    match the legacy tagged-string format at all, or
    :class:`LegacyValidationError` if they parse fine but don't resemble
    a Preferences dump. Never raises for a locally-recoverable problem
    inside one section or one history entry — those are skipped and
    recorded in the returned snapshot's ``warnings``.
    """
    try:
        raw_json = json.loads(raw_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise LegacyCodecError(f"not valid JSON: {exc}") from exc

    if not isinstance(raw_json, dict):
        raise LegacyValidationError(
            f"expected a JSON object at the top level, got {type(raw_json).__name__}"
        )

    decoded = decode(raw_json)
    if not isinstance(decoded, dict):
        raise LegacyValidationError("top level decoded to something other than a mapping")

    present_sections = _KNOWN_SECTIONS.intersection(decoded.keys())
    if not present_sections:
        raise LegacyValidationError(
            "no known TwitchLink Preferences section found at the top level "
            f"(expected one of {sorted(_KNOWN_SECTIONS)}, found {sorted(decoded.keys())})"
        )

    warnings: list[str] = []

    account_secret = _read_account(decoded.get("account"), warnings)
    general = _read_general(decoded.get("general"), warnings)
    advanced = _read_advanced(decoded.get("advanced"), warnings)
    localization = _read_localization(decoded.get("localization"), warnings)
    download = _read_download(decoded.get("download"), decoded.get("temp"), warnings)
    scheduled = _read_scheduled_downloads(decoded.get("scheduledDownloads"), warnings)
    history = _read_download_history(decoded.get("temp"), warnings)

    return LegacyPreferencesSnapshot(
        account_secret=account_secret,
        general=general,
        advanced=advanced,
        localization=localization,
        download=download,
        scheduled_downloads=scheduled,
        download_history=history,
        warnings=tuple(warnings),
    )


# --- per-section extraction (each tolerant of a missing/malformed section) --


def _as_legacy_object(
    value: Any, expected_class_name: str, warnings: list[str], where: str
) -> LegacyObject | None:
    if value is None:
        return None
    if not isinstance(value, LegacyObject):
        warnings.append(f"{where}: expected an object, got {type(value).__name__} — skipped")
        return None
    if value.class_name != expected_class_name:
        warnings.append(
            f"{where}: expected a {expected_class_name!r}, got {value.class_name!r} — skipped"
        )
        return None
    return value


def _read_account(raw: Any, warnings: list[str]) -> LegacyAccountSecret | None:
    account = _as_legacy_object(raw, "Account", warnings, "account")
    if account is None:
        return None
    pair = account.get("_accountData")
    if not isinstance(pair, tuple) or len(pair) != 2:
        if pair is not None:
            warnings.append("account._accountData: expected a 2-tuple — skipped")
        return None
    user, token_obj = pair
    if not isinstance(token_obj, LegacyObject) or "value" not in token_obj:
        return None  # not signed in — not a warning, just nothing to migrate
    token_value = token_obj.get("value")
    if not token_value:
        warnings.append("account: OAuth token object present but empty — skipped")
        return None
    platform_user_id = None
    username = None
    if isinstance(user, LegacyObject):
        raw_id = user.get("id")
        platform_user_id = str(raw_id) if raw_id else None
        username = user.get("login") or None
    return LegacyAccountSecret(
        token=token_value,
        platform_user_id=platform_user_id,
        username=username,
        expiration=token_obj.get("expiration"),
    )


def _read_general(raw: Any, warnings: list[str]) -> LegacyGeneralSection:
    general = _as_legacy_object(raw, "General", warnings, "general")
    if general is None:
        return LegacyGeneralSection()
    raw_bookmarks = general.get("_bookmarks") or []
    if not isinstance(raw_bookmarks, list):
        warnings.append("general._bookmarks: expected a list — treated as empty")
        raw_bookmarks = []
    bookmarks = tuple(
        login.strip().lower() for login in raw_bookmarks if isinstance(login, str) and login.strip()
    )
    return LegacyGeneralSection(
        notify=general.get("_notify"),
        use_system_tray=general.get("_useSystemTray"),
        bookmarks=bookmarks,
    )


def _read_advanced(raw: Any, warnings: list[str]) -> LegacyAdvancedSection:
    advanced = _as_legacy_object(raw, "Advanced", warnings, "advanced")
    if advanced is None:
        return LegacyAdvancedSection()
    return LegacyAdvancedSection(theme_mode=advanced.get("_themeMode"))


def _read_localization(raw: Any, warnings: list[str]) -> LegacyLocalizationSection:
    localization = _as_legacy_object(raw, "Localization", warnings, "localization")
    if localization is None:
        return LegacyLocalizationSection()
    return LegacyLocalizationSection(translation_pack_id=localization.get("_translationPackId"))


def _read_download(
    download_raw: Any, temp_raw: Any, warnings: list[str]
) -> LegacyDownloadSection:
    download = _as_legacy_object(download_raw, "Download", warnings, "download")
    speed = download.get("_downloadSpeed") if download is not None else None

    option_history: dict[str, LegacyDownloadOptionHistoryEntry] = {}
    temp = _as_legacy_object(temp_raw, "Temp", warnings, "temp")
    if temp is not None:
        raw_history = temp.get("_downloadOptionHistory") or {}
        if isinstance(raw_history, dict):
            for key, value in raw_history.items():
                if not isinstance(value, LegacyObject):
                    continue
                option_history[key] = LegacyDownloadOptionHistoryEntry(
                    directory=value.get("_directory"), file_format=value.get("_format")
                )
    return LegacyDownloadSection(download_speed=speed, option_history=option_history)


def _read_scheduled_downloads(raw: Any, warnings: list[str]) -> LegacyScheduledDownloadsSection:
    section = _as_legacy_object(raw, "ScheduledDownloads", warnings, "scheduledDownloads")
    if section is None:
        return LegacyScheduledDownloadsSection()
    enabled = bool(section.get("_enabled", False))
    raw_presets = section.get("_scheduledDownloadPresets") or []
    if not isinstance(raw_presets, list):
        warnings.append("scheduledDownloads._scheduledDownloadPresets: expected a list — ignored")
        raw_presets = []

    presets: list[LegacyScheduledDownloadPreset] = []
    for index, raw_preset in enumerate(raw_presets):
        where = f"scheduledDownloads._scheduledDownloadPresets[{index}]"
        preset = _as_legacy_object(raw_preset, "ScheduledDownloadPreset", warnings, where)
        if preset is None:
            continue
        channel_login = preset.get("channel")
        if not isinstance(channel_login, str) or not channel_login.strip():
            warnings.append(f"{where}: missing channel login — skipped")
            continue
        quality_index = preset.get("preferredQualityIndex", 0)
        in_range = isinstance(quality_index, int) and 0 <= quality_index < len(
            _LEGACY_QUALITY_INDEX
        )
        if not in_range:
            warnings.append(
                f"{where}: preferredQualityIndex {quality_index!r} out of range — "
                "defaulted to 'best'"
            )
            quality = "best"
        else:
            quality = _LEGACY_QUALITY_INDEX[quality_index]
        presets.append(
            LegacyScheduledDownloadPreset(
                channel_login=channel_login.strip().lower(),
                quality_preference=quality,
                enabled=bool(preset.get("enabled", True)),
                file_format=preset.get("fileFormat"),
                directory=preset.get("directory"),
            )
        )
    return LegacyScheduledDownloadsSection(enabled=enabled, presets=tuple(presets))


_CHANNEL_FIELD_BY_KIND = {"Stream": "broadcaster", "Video": "owner", "Clip": "broadcaster"}
_DURATION_FIELD_BY_KIND = {"Video": "lengthSeconds", "Clip": "durationSeconds"}


def _read_download_history(
    temp_raw: Any, warnings: list[str]
) -> tuple[LegacyDownloadHistoryEntry, ...]:
    temp = _as_legacy_object(temp_raw, "Temp", warnings, "temp")
    if temp is None:
        return ()
    raw_history = temp.get("_downloadHistory") or []
    if not isinstance(raw_history, list):
        warnings.append("temp._downloadHistory: expected a list — ignored")
        return ()

    entries: list[LegacyDownloadHistoryEntry] = []
    for index, raw_entry in enumerate(raw_history):
        where = f"temp._downloadHistory[{index}]"
        entry = _read_one_history_entry(raw_entry, where, warnings)
        if entry is not None:
            entries.append(entry)
    return tuple(entries)


def _read_one_history_entry(
    raw_entry: Any, where: str, warnings: list[str]
) -> LegacyDownloadHistoryEntry | None:
    history = _as_legacy_object(raw_entry, "DownloadHistory", warnings, where)
    if history is None:
        return None
    download_info = history.get("downloadInfo")
    if not isinstance(download_info, LegacyObject):
        warnings.append(f"{where}: missing downloadInfo — skipped")
        return None
    content = download_info.get("content")
    if not isinstance(content, LegacyObject) or content.class_name not in (
        "Stream",
        "Video",
        "Clip",
    ):
        warnings.append(
            f"{where}: downloadInfo.content is not a recognised Stream/Video/Clip — skipped"
        )
        return None
    content_id = content.get("id")
    if not content_id:
        warnings.append(f"{where}: content has no id — skipped")
        return None

    channel_field = _CHANNEL_FIELD_BY_KIND[content.class_name]
    channel = content.get(channel_field)
    channel_external_id = None
    if isinstance(channel, LegacyObject):
        raw_channel_id = channel.get("id")
        channel_external_id = str(raw_channel_id) if raw_channel_id else None

    duration_field = _DURATION_FIELD_BY_KIND.get(content.class_name)
    duration_seconds = None
    if duration_field is not None:
        raw_duration = content.get(duration_field)
        if isinstance(raw_duration, (int, float)) and raw_duration > 0:
            duration_seconds = int(raw_duration)

    result = history.get("result")
    if result is not None and result not in _RESULT_STATUS:
        warnings.append(f"{where}: unrecognised result {result!r} — treated as unknown")
        result = None

    progress_details = history.get("progressDetails")
    byte_size = None
    progress_ratio = None
    if isinstance(progress_details, LegacyObject):
        raw_byte_size = progress_details.get("byteSize")
        if isinstance(raw_byte_size, (int, float)) and raw_byte_size > 0:
            byte_size = int(raw_byte_size)
        total_ms = progress_details.get("totalMilliseconds")
        done_ms = progress_details.get("milliseconds")
        total_ok = isinstance(total_ms, (int, float)) and total_ms > 0
        if total_ok and isinstance(done_ms, (int, float)):
            progress_ratio = max(0.0, min(1.0, done_ms / total_ms))

    return LegacyDownloadHistoryEntry(
        media_kind=content.class_name.lower(),
        content_id=str(content_id),
        title=content.get("title") or "",
        channel_external_id=channel_external_id,
        duration_seconds=duration_seconds,
        directory=download_info.get("directory"),
        file_name=download_info.get("fileName"),
        file_format=download_info.get("fileFormat"),
        started_at=history.get("startedAt"),
        completed_at=history.get("completedAt"),
        result=result,
        error=history.get("error"),
        byte_size=byte_size,
        progress_ratio=progress_ratio,
    )
