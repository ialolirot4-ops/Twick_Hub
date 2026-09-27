from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

from twick_hub.infrastructure.migration import legacy_locator

# --- default_legacy_settings_path -------------------------------------------------


def test_windows_path_uses_appdata_env_var(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", r"C:\Users\test\AppData\Roaming")

    path = legacy_locator.default_legacy_settings_path()

    assert path == Path(r"C:\Users\test\AppData\Roaming") / "TwitchLink" / "settings.json"


def test_windows_path_is_none_without_appdata_env_var(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv("APPDATA", raising=False)

    assert legacy_locator.default_legacy_settings_path() is None


def test_macos_path_uses_application_support(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", lambda: Path("/Users/test"))

    path = legacy_locator.default_legacy_settings_path()

    assert path == Path("/Users/test/Library/Application Support/TwitchLink/settings.json")


def test_linux_has_no_known_legacy_path(monkeypatch):
    # TwitchLink 3.5.x shipped no Linux OSAdapter at all — see this
    # module's docstring. Confirmed by auditing the legacy repository in
    # this phase, not assumed.
    monkeypatch.setattr(sys, "platform", "linux")

    assert legacy_locator.default_legacy_settings_path() is None


# --- detect -------------------------------------------------


def test_detect_finds_an_existing_file(tmp_path: Path):
    settings_file = tmp_path / "settings.json"
    settings_file.write_text("{}")

    result = legacy_locator.detect(settings_file)

    assert result.found is True
    assert result.path == settings_file
    assert result.reason is None


def test_detect_reports_not_found_for_a_missing_file(tmp_path: Path):
    result = legacy_locator.detect(tmp_path / "nope.json")

    assert result.found is False
    assert result.path == tmp_path / "nope.json"
    assert result.reason is not None


def test_detect_reports_not_found_when_default_path_is_unavailable(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")

    result = legacy_locator.detect(None)

    assert result.found is False
    assert result.path is None
    assert result.reason is not None
    assert "OSAdapter" in result.reason


def test_detect_uses_the_default_path_when_none_is_given(tmp_path: Path, monkeypatch):
    settings_file = tmp_path / "TwitchLink" / "settings.json"
    settings_file.parent.mkdir()
    settings_file.write_text("{}")
    monkeypatch.setattr(legacy_locator, "default_legacy_settings_path", lambda: settings_file)

    result = legacy_locator.detect()

    assert result.found is True
    assert result.path == settings_file


# --- backup -------------------------------------------------


def test_backup_copies_the_file_byte_for_byte(tmp_path: Path):
    source = tmp_path / "settings.json"
    source.write_bytes(b'{"general": {}}')
    backup_dir = tmp_path / "backups"

    backup_path = legacy_locator.backup(source, backup_dir)

    assert backup_path.exists()
    assert backup_path.read_bytes() == source.read_bytes()
    assert backup_path.parent == backup_dir


def test_backup_never_modifies_the_source_file(tmp_path: Path):
    source = tmp_path / "settings.json"
    original_bytes = b'{"general": {}}'
    source.write_bytes(original_bytes)

    legacy_locator.backup(source, tmp_path / "backups")

    assert source.read_bytes() == original_bytes


def test_backup_creates_the_backup_directory_if_missing(tmp_path: Path):
    source = tmp_path / "settings.json"
    source.write_bytes(b"{}")
    backup_dir = tmp_path / "does" / "not" / "exist" / "yet"

    backup_path = legacy_locator.backup(source, backup_dir)

    assert backup_path.exists()


def test_repeated_backups_never_overwrite_an_earlier_one(tmp_path: Path):
    source = tmp_path / "settings.json"
    source.write_bytes(b"{}")
    backup_dir = tmp_path / "backups"

    first = legacy_locator.backup(source, backup_dir, now=datetime(2026, 1, 1, 10, 0, 0, 0))
    second = legacy_locator.backup(source, backup_dir, now=datetime(2026, 1, 1, 10, 0, 0, 1))

    assert first != second
    assert first.exists()
    assert second.exists()
    assert len(list(backup_dir.iterdir())) == 2


def test_backup_filename_is_stable_given_an_explicit_now(tmp_path: Path):
    source = tmp_path / "settings.json"
    source.write_bytes(b"{}")

    backup_path = legacy_locator.backup(
        source, tmp_path / "backups", now=datetime(2026, 1, 15, 9, 30, 0)
    )

    assert backup_path.name == "settings.20260115T093000000000.json.bak"


def test_backup_raises_if_the_copy_comes_out_a_different_size(tmp_path: Path, monkeypatch):
    """A truncated or otherwise short copy must never be silently trusted
    as a valid backup — the reversibility net FASE 15's rollback depends
    on would be lying about what it actually preserved."""
    source = tmp_path / "settings.json"
    source.write_bytes(b"the original legacy settings content")
    backup_dir = tmp_path / "backups"

    def _truncated_copy(src, dst) -> None:
        Path(dst).write_bytes(Path(src).read_bytes()[:5])  # deliberately short

    monkeypatch.setattr(legacy_locator.shutil, "copy2", _truncated_copy)

    with pytest.raises(OSError, match="size mismatch"):
        legacy_locator.backup(source, backup_dir)
