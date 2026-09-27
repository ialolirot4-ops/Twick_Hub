from __future__ import annotations

import json
from datetime import datetime

import pytest

from twick_hub.infrastructure.migration.legacy_codec import LegacyCodecError
from twick_hub.infrastructure.migration.legacy_reader import (
    LegacyValidationError,
    parse_snapshot,
    read_legacy_file,
    sha256_of,
)


def _obj(class_name: str, module: str = "AppData.Preferences", **fields):
    return {"__type__": f"obj:{module}:{class_name}", **fields}


def _str(value: str) -> str:
    return f"str:{value}"


def _user(user_id: str, login: str) -> dict:
    return _obj(
        "User",
        module="Services.Twitch.GQL.TwitchGQLModels",
        id=_str(user_id),
        login=_str(login),
        displayName=_str(login),
    )


def _token(value: str, expiration: str | None = "datetime:2027-01-01T00:00:00.000Z") -> dict:
    fields = {"value": _str(value)}
    if expiration is not None:
        fields["expiration"] = expiration
    return _obj("OAuthToken", module="Services.Twitch.Authentication.OAuth.OAuthToken", **fields)


# --- top-level validation -------------------------------------------------


def test_sha256_of_is_stable_and_lowercase_hex():
    digest = sha256_of(b"hello")
    assert digest == digest.lower()
    assert len(digest) == 64


def test_read_legacy_file_returns_raw_bytes(tmp_path):
    path = tmp_path / "settings.json"
    path.write_bytes(b'{"general": {}}')

    assert read_legacy_file(path) == b'{"general": {}}'


def test_invalid_json_raises_codec_error():
    with pytest.raises(LegacyCodecError):
        parse_snapshot(b"not json")


def test_non_object_top_level_raises_validation_error():
    with pytest.raises(LegacyValidationError):
        parse_snapshot(b"[1, 2, 3]")


def test_top_level_decoding_to_something_other_than_a_mapping_raises_validation_error():
    """Distinct from the case above: there, the raw JSON itself isn't an
    object at all. Here the raw JSON IS a JSON object, but its own
    ``__type__`` tag makes it decode to something else entirely (a tuple)
    — the check right after decoding, not the one before it."""
    payload = {"__type__": "tuple", "data": []}
    with pytest.raises(LegacyValidationError):
        parse_snapshot(json.dumps(payload).encode())


def test_no_known_section_raises_validation_error():
    with pytest.raises(LegacyValidationError):
        parse_snapshot(json.dumps({"somethingElse": 1}).encode())


def test_a_file_with_only_one_known_section_is_accepted():
    payload = {"general": _obj("General", _notify=True, _bookmarks=[])}
    snapshot = parse_snapshot(json.dumps(payload).encode())
    assert snapshot.general.notify is True
    assert snapshot.account_secret is None


# --- account -------------------------------------------------


def test_signed_in_account_extracts_the_token_and_metadata():
    payload = {
        "account": _obj(
            "Account",
            _accountData={
                "__type__": "tuple",
                "data": [_user("123", "someone"), _token("SECRET-VALUE")],
            },
        )
    }

    snapshot = parse_snapshot(json.dumps(payload).encode())

    assert snapshot.account_secret is not None
    assert snapshot.account_secret.token == "SECRET-VALUE"
    assert snapshot.account_secret.platform_user_id == "123"
    assert snapshot.account_secret.username == "someone"
    assert snapshot.account_secret.expiration == datetime(2027, 1, 1)


def test_signed_out_account_has_no_secret():
    payload = {
        "account": _obj("Account", _accountData={"__type__": "tuple", "data": [None, None]})
    }

    snapshot = parse_snapshot(json.dumps(payload).encode())

    assert snapshot.account_secret is None


def test_account_with_no_token_value_is_treated_as_signed_out():
    payload = {
        "account": _obj(
            "Account",
            _accountData={
                "__type__": "tuple",
                "data": [_user("123", "someone"), _obj("OAuthToken")],
            },
        )
    }

    snapshot = parse_snapshot(json.dumps(payload).encode())

    assert snapshot.account_secret is None


def test_missing_account_section_has_no_secret_and_no_warning():
    snapshot = parse_snapshot(json.dumps({"general": _obj("General")}).encode())
    assert snapshot.account_secret is None
    assert snapshot.warnings == ()


def test_account_data_that_is_not_a_legacy_object_at_all_is_skipped_with_a_warning():
    """Distinct from test_general_section_of_the_wrong_class_is_skipped_with_a_warning
    below — that section IS a LegacyObject, just the wrong class. A plain
    JSON object with no ``__type__`` tag decodes to a bare Python dict,
    not a LegacyObject at all — a different, less specific failure."""
    payload = {"account": {"just": "a plain untagged dict"}}

    snapshot = parse_snapshot(json.dumps(payload).encode())

    assert snapshot.account_secret is None
    assert any("expected an object, got dict" in w for w in snapshot.warnings)


def test_account_data_pair_of_the_wrong_length_is_skipped_with_a_warning():
    payload = {
        "account": _obj(
            "Account", _accountData={"__type__": "tuple", "data": [_user("1", "solo")]}
        )
    }

    snapshot = parse_snapshot(json.dumps(payload).encode())

    assert snapshot.account_secret is None
    assert any("expected a 2-tuple" in w for w in snapshot.warnings)


def test_account_with_an_empty_token_value_is_skipped_with_a_warning():
    """Distinct from test_account_with_no_token_value_is_treated_as_signed_out
    above, where the ``OAuthToken`` object has no ``value`` field at all
    (a normal, unremarkable signed-out state). Here the field is present
    but empty — worth a warning, since that shape shouldn't normally
    happen for an object that otherwise looks like a real token."""
    payload = {
        "account": _obj(
            "Account",
            _accountData={
                "__type__": "tuple",
                "data": [_user("123", "someone"), _obj("OAuthToken", value=_str(""))],
            },
        )
    }

    snapshot = parse_snapshot(json.dumps(payload).encode())

    assert snapshot.account_secret is None
    assert any("token object present but empty" in w for w in snapshot.warnings)


# --- general / bookmarks -------------------------------------------------


def test_bookmarks_are_lowercased_stripped_and_blanks_dropped():
    payload = {"general": _obj("General", _bookmarks=[_str("Shroud"), _str("  "), _str("Ninja")])}

    snapshot = parse_snapshot(json.dumps(payload).encode())

    assert snapshot.general.bookmarks == ("shroud", "ninja")


def test_bookmarks_that_are_not_a_list_are_treated_as_empty_with_a_warning():
    payload = {"general": _obj("General", _bookmarks=_str("not-a-list"))}

    snapshot = parse_snapshot(json.dumps(payload).encode())

    assert snapshot.general.bookmarks == ()
    assert any("_bookmarks: expected a list" in w for w in snapshot.warnings)


def test_general_section_of_the_wrong_class_is_skipped_with_a_warning():
    payload = {"general": _obj("SomethingElse")}

    snapshot = parse_snapshot(json.dumps(payload).encode())

    assert snapshot.general.bookmarks == ()
    assert any("SomethingElse" in w for w in snapshot.warnings)


# --- advanced / localization -------------------------------------------------


@pytest.mark.parametrize("mode", ["", "light", "dark"])
def test_theme_mode_is_read_verbatim(mode):
    payload = {"advanced": _obj("Advanced", _themeMode=_str(mode) if mode else "str:")}
    snapshot = parse_snapshot(json.dumps(payload).encode())
    assert snapshot.advanced.theme_mode == mode


def test_translation_pack_id_is_read():
    payload = {"localization": _obj("Localization", _translationPackId=_str("es"))}
    snapshot = parse_snapshot(json.dumps(payload).encode())
    assert snapshot.localization.translation_pack_id == "es"


# --- download / option history -------------------------------------------------


def test_download_speed_is_read():
    payload = {"download": _obj("Download", _downloadSpeed=7)}
    snapshot = parse_snapshot(json.dumps(payload).encode())
    assert snapshot.download.download_speed == 7


def test_option_history_directory_and_format_are_read_per_content_type():
    payload = {
        "temp": _obj(
            "Temp",
            _downloadOptionHistory={
                "__type__": "dict",
                "StreamHistory": _obj(
                    "StreamHistory",
                    module="Download.History.DownloadOptionHistory",
                    _directory=_str("D:/Streams"),
                    _format=_str("mp4"),
                ),
                "VideoHistory": _obj(
                    "VideoHistory",
                    module="Download.History.DownloadOptionHistory",
                    _directory=_str("D:/Videos"),
                    _format=_str("ts"),
                ),
            },
        )
    }

    snapshot = parse_snapshot(json.dumps(payload).encode())

    assert snapshot.download.option_history["StreamHistory"].directory == "D:/Streams"
    assert snapshot.download.option_history["StreamHistory"].file_format == "mp4"
    assert snapshot.download.option_history["VideoHistory"].file_format == "ts"


# --- scheduled downloads -------------------------------------------------


def _preset(channel: str, quality_index: int, enabled: bool = True) -> dict:
    return _obj(
        "ScheduledDownloadPreset",
        module="Download.ScheduledDownloadPreset",
        channel=_str(channel),
        preferredQualityIndex=quality_index,
        fileFormat=_str("mp4"),
        directory=_str("D:/Recordings"),
        enabled=enabled,
    )


@pytest.mark.parametrize(
    "index,expected",
    [
        (0, "best"), (1, "1080p"), (2, "720p"), (3, "480p"),
        (4, "360p"), (5, "160p"), (6, "worst"), (7, "audio-only"),
    ],  # fmt: skip
)
def test_every_legacy_quality_index_maps_to_the_right_label(index, expected):
    payload = {
        "scheduledDownloads": _obj(
            "ScheduledDownloads", _enabled=True, _scheduledDownloadPresets=[_preset("x", index)]
        )
    }

    snapshot = parse_snapshot(json.dumps(payload).encode())

    assert snapshot.scheduled_downloads.presets[0].quality_preference == expected


def test_out_of_range_quality_index_defaults_to_best_with_a_warning():
    payload = {
        "scheduledDownloads": _obj(
            "ScheduledDownloads", _enabled=True, _scheduledDownloadPresets=[_preset("x", 999)]
        )
    }

    snapshot = parse_snapshot(json.dumps(payload).encode())

    assert snapshot.scheduled_downloads.presets[0].quality_preference == "best"
    assert any("out of range" in w for w in snapshot.warnings)


def test_preset_missing_a_channel_login_is_skipped():
    broken = _obj(
        "ScheduledDownloadPreset",
        module="Download.ScheduledDownloadPreset",
        preferredQualityIndex=0,
    )
    payload = {
        "scheduledDownloads": _obj(
            "ScheduledDownloads", _enabled=True, _scheduledDownloadPresets=[broken]
        )
    }

    snapshot = parse_snapshot(json.dumps(payload).encode())

    assert snapshot.scheduled_downloads.presets == ()
    assert any("missing channel" in w for w in snapshot.warnings)


def test_channel_login_is_lowercased_and_stripped():
    payload = {
        "scheduledDownloads": _obj(
            "ScheduledDownloads", _enabled=True, _scheduledDownloadPresets=[_preset("XQC", 0)]
        )
    }

    snapshot = parse_snapshot(json.dumps(payload).encode())

    assert snapshot.scheduled_downloads.presets[0].channel_login == "xqc"


def test_disabled_master_switch_is_recorded_but_presets_keep_their_own_flag():
    payload = {
        "scheduledDownloads": _obj(
            "ScheduledDownloads",
            _enabled=False,
            _scheduledDownloadPresets=[_preset("x", 0, enabled=True)],
        )
    }

    snapshot = parse_snapshot(json.dumps(payload).encode())

    assert snapshot.scheduled_downloads.enabled is False
    assert snapshot.scheduled_downloads.presets[0].enabled is True


# --- download history -------------------------------------------------


def _history_entry(
    kind: str,
    content_id: str,
    channel_field: str,
    channel_id: str,
    result: str | None = "download-complete",
    extra_content_fields: dict | None = None,
):
    content = _obj(
        kind,
        module="Services.Twitch.GQL.TwitchGQLModels",
        id=_str(content_id),
        title=_str("A title"),
        **{channel_field: _user(channel_id, "achannel")},
        **(extra_content_fields or {}),
    )
    download_info = _obj(
        f"{kind}DownloadInfo",
        module="Download.DownloadInfo",
        content=content,
        directory=_str("D:/Downloads"),
        fileName=_str("a-file"),
        fileFormat=_str("mp4"),
    )
    fields = {
        "downloadInfo": download_info,
        "startedAt": "datetime:2026-01-01T00:00:00.000Z",
        "completedAt": "datetime:2026-01-01T01:00:00.000Z",
    }
    if result is not None:
        fields["result"] = _str(result)
    return _obj("DownloadHistory", module="Download.History.DownloadHistory", **fields)


def test_a_valid_stream_history_entry_is_read():
    payload = {
        "temp": _obj(
            "Temp",
            _downloadHistory=[
                _history_entry("Stream", "111", "broadcaster", "222"),
            ],
        )
    }

    snapshot = parse_snapshot(json.dumps(payload).encode())

    assert len(snapshot.download_history) == 1
    entry = snapshot.download_history[0]
    assert entry.media_kind == "stream"
    assert entry.content_id == "111"
    assert entry.channel_external_id == "222"
    assert entry.title == "A title"
    assert entry.result == "download-complete"


def test_video_history_reads_owner_as_the_channel_and_length_as_duration():
    payload = {
        "temp": _obj(
            "Temp",
            _downloadHistory=[
                _history_entry(
                    "Video", "333", "owner", "444", extra_content_fields={"lengthSeconds": 120.0}
                ),
            ],
        )
    }

    snapshot = parse_snapshot(json.dumps(payload).encode())

    entry = snapshot.download_history[0]
    assert entry.media_kind == "video"
    assert entry.channel_external_id == "444"
    assert entry.duration_seconds == 120


def test_clip_history_reads_broadcaster_and_duration_seconds_field():
    payload = {
        "temp": _obj(
            "Temp",
            _downloadHistory=[
                _history_entry(
                    "Clip",
                    "555",
                    "broadcaster",
                    "666",
                    extra_content_fields={"durationSeconds": 30.0},
                ),
            ],
        )
    }

    snapshot = parse_snapshot(json.dumps(payload).encode())

    entry = snapshot.download_history[0]
    assert entry.media_kind == "clip"
    assert entry.duration_seconds == 30


def test_entry_with_no_content_is_skipped_not_fatal():
    broken = _obj(
        "DownloadHistory",
        module="Download.History.DownloadHistory",
        downloadInfo=_obj(
            "StreamDownloadInfo",
            module="Download.DownloadInfo",
            content=None,
            directory=_str("D:/Downloads"),
            fileName=_str("x"),
            fileFormat=_str("mp4"),
        ),
        startedAt="datetime:2026-01-01T00:00:00.000Z",
        result=_str("download-complete"),
    )
    payload = {"temp": _obj("Temp", _downloadHistory=[broken])}

    snapshot = parse_snapshot(json.dumps(payload).encode())

    assert snapshot.download_history == ()
    assert any("content" in w for w in snapshot.warnings)


def test_one_malformed_entry_does_not_abort_reading_the_rest():
    good = _history_entry("Stream", "1", "broadcaster", "2")
    broken = _obj(
        "DownloadHistory",
        module="Download.History.DownloadHistory",
        downloadInfo=_obj(
            "StreamDownloadInfo", module="Download.DownloadInfo", content=None
        ),
    )
    payload = {"temp": _obj("Temp", _downloadHistory=[broken, good])}

    snapshot = parse_snapshot(json.dumps(payload).encode())

    assert len(snapshot.download_history) == 1
    assert snapshot.download_history[0].content_id == "1"


def test_progress_ratio_is_computed_from_progress_details():
    entry = _history_entry("Stream", "1", "broadcaster", "2", result="download-aborted")
    entry["progressDetails"] = _obj(
        "DownloadProgressDetails",
        module="Download.DownloadProgressDetails",
        byteSize=5000,
        milliseconds=250,
        totalMilliseconds=1000,
    )
    payload = {"temp": _obj("Temp", _downloadHistory=[entry])}

    snapshot = parse_snapshot(json.dumps(payload).encode())

    result_entry = snapshot.download_history[0]
    assert result_entry.byte_size == 5000
    assert result_entry.progress_ratio == 0.25


def test_unrecognised_result_value_is_treated_as_unknown_with_a_warning():
    entry = _history_entry("Stream", "1", "broadcaster", "2", result="some-future-result")
    payload = {"temp": _obj("Temp", _downloadHistory=[entry])}

    snapshot = parse_snapshot(json.dumps(payload).encode())

    assert snapshot.download_history[0].result is None
    assert any("unrecognised result" in w for w in snapshot.warnings)
