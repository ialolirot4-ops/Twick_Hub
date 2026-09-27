from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from twick_hub.domain.enums import DownloadStatus, Platform, ScheduleTrigger, Theme
from twick_hub.domain.value_objects import PlatformRef
from twick_hub.infrastructure.migration import legacy_transform
from twick_hub.infrastructure.migration.legacy_reader import (
    LegacyAdvancedSection,
    LegacyDownloadHistoryEntry,
    LegacyDownloadOptionHistoryEntry,
    LegacyDownloadSection,
    LegacyGeneralSection,
    LegacyLocalizationSection,
    LegacyPreferencesSnapshot,
    LegacyScheduledDownloadPreset,
)

_REF = PlatformRef(platform=Platform.TWITCH, external_id="999")


def _snapshot(**overrides) -> LegacyPreferencesSnapshot:
    return LegacyPreferencesSnapshot(**overrides)


def _history_entry(**overrides) -> LegacyDownloadHistoryEntry:
    fields: dict[str, Any] = dict(
        media_kind="stream",
        content_id="111",
        title="A stream",
        channel_external_id="222",
        duration_seconds=None,
        directory="D:/Downloads",
        file_name="a-file",
        file_format="mp4",
        started_at=datetime(2026, 1, 1, 10, 0),
        completed_at=datetime(2026, 1, 1, 11, 0),
        result="download-complete",
        error=None,
        byte_size=1000,
        progress_ratio=None,
    )
    fields.update(overrides)
    return LegacyDownloadHistoryEntry(**fields)


def _preset(**overrides) -> LegacyScheduledDownloadPreset:
    fields: dict[str, Any] = dict(
        channel_login="xqc", quality_preference="720p", enabled=True, file_format="mp4",
        directory="D:/Recordings",
    )  # fmt: skip
    fields.update(overrides)
    return LegacyScheduledDownloadPreset(**fields)


# --- deterministic_id -------------------------------------------------


def test_deterministic_id_is_stable_across_calls():
    a = legacy_transform.deterministic_id("download_history", "stream", "1")
    b = legacy_transform.deterministic_id("download_history", "stream", "1")
    assert a == b


def test_deterministic_id_differs_by_kind():
    a = legacy_transform.deterministic_id("download_history", "1")
    b = legacy_transform.deterministic_id("scheduled_download", "1")
    assert a != b


def test_deterministic_id_differs_by_parts():
    a = legacy_transform.deterministic_id("download_history", "1")
    b = legacy_transform.deterministic_id("download_history", "2")
    assert a != b


def test_deterministic_id_looks_like_a_uuid_hex():
    result = legacy_transform.deterministic_id("x", "y")
    assert len(result) == 32
    int(result, 16)  # must not raise


# --- settings_overrides_from_legacy -------------------------------------------------


def test_empty_snapshot_produces_no_overrides():
    assert legacy_transform.settings_overrides_from_legacy(_snapshot()) == {}


def test_general_section_maps_tray_and_notifications():
    snapshot = _snapshot(general=LegacyGeneralSection(notify=False, use_system_tray=True))
    overrides = legacy_transform.settings_overrides_from_legacy(snapshot)
    assert overrides["notifications_enabled"] is False
    assert overrides["minimize_to_tray"] is True


@pytest.mark.parametrize(
    "mode,theme", [("", Theme.SYSTEM), ("light", Theme.LIGHT), ("dark", Theme.DARK)]
)
def test_theme_mode_maps_to_the_right_theme(mode, theme):
    snapshot = _snapshot(advanced=LegacyAdvancedSection(theme_mode=mode))
    overrides = legacy_transform.settings_overrides_from_legacy(snapshot)
    assert overrides["theme"] is theme


def test_translation_pack_id_maps_to_language():
    snapshot = _snapshot(localization=LegacyLocalizationSection(translation_pack_id="ko"))
    overrides = legacy_transform.settings_overrides_from_legacy(snapshot)
    assert overrides["language"] == "ko"


def test_download_speed_maps_to_max_concurrent_downloads():
    snapshot = _snapshot(download=LegacyDownloadSection(download_speed=9))
    overrides = legacy_transform.settings_overrides_from_legacy(snapshot)
    assert overrides["max_concurrent_downloads"] == 9


def test_download_speed_is_clamped_to_at_least_one():
    snapshot = _snapshot(download=LegacyDownloadSection(download_speed=0))
    overrides = legacy_transform.settings_overrides_from_legacy(snapshot)
    assert overrides["max_concurrent_downloads"] == 1


def test_stream_option_history_maps_to_default_directory_and_format():
    snapshot = _snapshot(
        download=LegacyDownloadSection(
            option_history={
                "StreamHistory": LegacyDownloadOptionHistoryEntry(
                    directory="D:/Streams", file_format="mp4"
                ),
                "VideoHistory": LegacyDownloadOptionHistoryEntry(
                    directory="D:/Videos", file_format="ts"
                ),
            }
        )
    )
    overrides = legacy_transform.settings_overrides_from_legacy(snapshot)
    # StreamHistory wins — VideoHistory's own directory/format is a
    # documented, deliberate gap (see this module's docstring).
    assert overrides["default_directory"] == "D:/Streams"
    assert overrides["default_format"] == "mp4"


def test_missing_stream_option_history_leaves_directory_and_format_unset():
    snapshot = _snapshot(
        download=LegacyDownloadSection(
            option_history={
                "VideoHistory": LegacyDownloadOptionHistoryEntry(directory="D:/Videos")
            }
        )
    )
    overrides = legacy_transform.settings_overrides_from_legacy(snapshot)
    assert "default_directory" not in overrides
    assert "default_format" not in overrides


# --- scheduled_download_from_preset -------------------------------------------------


def test_preset_becomes_a_recurring_scheduled_download():
    result = legacy_transform.scheduled_download_from_preset(
        _preset(), channel_ref=_REF, master_enabled=True
    )
    assert result.trigger is ScheduleTrigger.RECURRING
    assert result.channel_ref == _REF
    assert result.quality_preference == "720p"
    assert result.download_directory == "D:/Recordings"
    assert result.preferred_format == "mp4"


def test_preset_is_active_only_when_both_the_item_and_master_switch_are_on():
    assert legacy_transform.scheduled_download_from_preset(
        _preset(enabled=True), channel_ref=_REF, master_enabled=True
    ).is_active
    assert not legacy_transform.scheduled_download_from_preset(
        _preset(enabled=False), channel_ref=_REF, master_enabled=True
    ).is_active
    assert not legacy_transform.scheduled_download_from_preset(
        _preset(enabled=True), channel_ref=_REF, master_enabled=False
    ).is_active


def test_scheduled_download_id_is_deterministic_per_channel():
    a = legacy_transform.scheduled_download_from_preset(
        _preset(), channel_ref=_REF, master_enabled=True
    )
    b = legacy_transform.scheduled_download_from_preset(
        _preset(quality_preference="best"), channel_ref=_REF, master_enabled=True
    )
    assert a.id == b.id  # same channel -> same id, regardless of other fields


# --- download_from_history_entry -------------------------------------------------


def test_completed_entry_maps_to_completed_status_and_full_progress():
    result = legacy_transform.download_from_history_entry(_history_entry(), channel_ref=_REF)
    assert result.status is DownloadStatus.COMPLETED
    assert result.progress_percent == 100.0
    assert result.media.channel_ref == _REF
    assert result.destination_path == "D:/Downloads/a-file.mp4"
    assert result.file_size_bytes == 1000


@pytest.mark.parametrize(
    "result_value,expected_status",
    [
        ("download-complete", DownloadStatus.COMPLETED),
        ("download-stopped", DownloadStatus.CANCELLED),
        ("download-canceled", DownloadStatus.CANCELLED),
        ("download-aborted", DownloadStatus.FAILED),
        ("downloading", DownloadStatus.FAILED),
        (None, DownloadStatus.FAILED),
    ],
)
def test_every_legacy_result_maps_to_the_right_status(result_value, expected_status):
    entry = _history_entry(result=result_value)
    result = legacy_transform.download_from_history_entry(entry, channel_ref=_REF)
    assert result.status is expected_status


def test_interrupted_downloading_status_gets_an_explanatory_error_message():
    entry = _history_entry(result="downloading", error=None)
    result = legacy_transform.download_from_history_entry(entry, channel_ref=_REF)
    assert result.error_message is not None
    assert "interrupted" in result.error_message


def test_existing_error_message_is_preserved():
    entry = _history_entry(result="download-aborted", error="connection-lost")
    result = legacy_transform.download_from_history_entry(entry, channel_ref=_REF)
    assert result.error_message == "connection-lost"


def test_incomplete_entry_uses_progress_ratio_when_available():
    entry = _history_entry(result="download-aborted", progress_ratio=0.4)
    result = legacy_transform.download_from_history_entry(entry, channel_ref=_REF)
    assert result.progress_percent == 40.0


def test_incomplete_entry_without_progress_ratio_defaults_to_zero():
    entry = _history_entry(result="download-aborted", progress_ratio=None)
    result = legacy_transform.download_from_history_entry(entry, channel_ref=_REF)
    assert result.progress_percent == 0.0


def test_missing_file_parts_fall_back_to_a_placeholder_destination():
    entry = _history_entry(directory="D:/Downloads", file_name=None, file_format=None)
    result = legacy_transform.download_from_history_entry(entry, channel_ref=_REF)
    assert result.destination_path == "D:/Downloads"


def test_missing_directory_and_file_parts_uses_the_fallback_message():
    entry = _history_entry(directory=None, file_name=None, file_format=None)
    result = legacy_transform.download_from_history_entry(entry, channel_ref=_REF)
    assert "unknown" in result.destination_path.lower()


def test_no_channel_ref_is_allowed():
    result = legacy_transform.download_from_history_entry(_history_entry(), channel_ref=None)
    assert result.media.channel_ref is None


def test_duration_is_carried_onto_media_when_present():
    entry = _history_entry(duration_seconds=120)
    result = legacy_transform.download_from_history_entry(entry, channel_ref=_REF)
    assert result.media.duration is not None
    assert result.media.duration.total_seconds == 120


def test_missing_started_at_falls_back_to_completed_at():
    entry = _history_entry(started_at=None, completed_at=datetime(2026, 1, 2, 0, 0))
    result = legacy_transform.download_from_history_entry(entry, channel_ref=_REF)
    assert result.created_at == datetime(2026, 1, 2, 0, 0)


def test_download_id_is_deterministic_given_the_same_entry():
    entry = _history_entry()
    a = legacy_transform.download_from_history_entry(entry, channel_ref=_REF)
    b = legacy_transform.download_from_history_entry(entry, channel_ref=None)
    assert a.id == b.id  # channel_ref doesn't affect identity, only content+timing


def test_download_id_differs_for_different_content():
    a = legacy_transform.download_from_history_entry(
        _history_entry(content_id="1"), channel_ref=_REF
    )
    b = legacy_transform.download_from_history_entry(
        _history_entry(content_id="2"), channel_ref=_REF
    )
    assert a.id != b.id
