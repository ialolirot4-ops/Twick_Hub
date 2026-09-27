from __future__ import annotations

import sys
from pathlib import Path

from twick_hub.config.settings import AppConfig, default_data_dir, load_config


def test_defaults_are_safe_with_zero_configuration(tmp_path):
    config = AppConfig(data_dir=tmp_path)
    assert config.app_name == "Twick Hub"
    assert config.resolved_database_url().startswith("sqlite:///")


def test_explicit_database_url_wins_over_default(tmp_path):
    config = AppConfig(data_dir=tmp_path, database_url="sqlite:///:memory:")
    assert config.resolved_database_url() == "sqlite:///:memory:"


def test_resolved_database_url_creates_data_dir(tmp_path):
    target = tmp_path / "nested" / "dir"
    config = AppConfig(data_dir=target)
    config.resolved_database_url()
    assert target.is_dir()


# FASE 18 — Testing: every test above only ever exercises whichever branch
# of ``default_data_dir()`` matches the platform this suite happens to run
# on (Linux, in this sandbox). These pin down the other two explicitly, by
# forcing ``sys.platform`` rather than relying on where the tests run.


def test_default_data_dir_on_windows_uses_appdata(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", r"C:\Users\test\AppData\Roaming")
    assert default_data_dir() == Path(r"C:\Users\test\AppData\Roaming") / "TwickHub"


def test_default_data_dir_on_windows_falls_back_without_appdata(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv("APPDATA", raising=False)
    assert default_data_dir() == Path.home() / "AppData" / "Roaming" / "TwickHub"


def test_default_data_dir_on_macos(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert default_data_dir() == Path.home() / "Library" / "Application Support" / "TwickHub"


def test_load_config_reads_settings_from_the_environment(monkeypatch):
    monkeypatch.setenv("TWICK_HUB_APP_NAME", "Custom Name")
    monkeypatch.setenv("TWICK_HUB_LOG_LEVEL", "DEBUG")

    config = load_config()

    assert config.app_name == "Custom Name"
    assert config.log_level == "DEBUG"
