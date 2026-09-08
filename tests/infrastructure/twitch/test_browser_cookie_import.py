from __future__ import annotations

import textwrap

import pytest

import twick_hub.infrastructure.twitch.browser_cookie_import as browser_cookie_import
from twick_hub.infrastructure.twitch.browser_cookie_import import FirefoxCookieImporter
from twick_hub.infrastructure.twitch.errors import NoBrowserSessionFoundError

_SAMPLE_PROFILES_INI = textwrap.dedent(
    """
    [Profile1]
    Name=default
    IsRelative=1
    Path=xxxxxxxx.default
    Default=1

    [Profile0]
    Name=work
    IsRelative=1
    Path=yyyyyyyy.work

    [General]
    StartWithLastProfile=1
    """
).strip()


def test_list_profiles_parses_only_profile_sections(tmp_path, monkeypatch):
    ini_path = tmp_path / "profiles.ini"
    ini_path.write_text(_SAMPLE_PROFILES_INI, encoding="utf-8")
    monkeypatch.setattr(browser_cookie_import, "_firefox_profiles_ini_path", lambda: str(ini_path))

    profiles = FirefoxCookieImporter().list_profiles()

    assert {p.display_name for p in profiles} == {"default", "work"}
    assert {p.key for p in profiles} == {"xxxxxxxx.default", "yyyyyyyy.work"}


def test_list_profiles_raises_when_firefox_is_not_installed(tmp_path, monkeypatch):
    missing_path = tmp_path / "does-not-exist" / "profiles.ini"

    def fake_path() -> str:
        return str(missing_path)

    monkeypatch.setattr(browser_cookie_import, "_firefox_profiles_ini_path", fake_path)

    with pytest.raises(NoBrowserSessionFoundError, match="Firefox"):
        FirefoxCookieImporter().list_profiles()


def test_list_profiles_with_no_profile_sections_returns_empty(tmp_path, monkeypatch):
    ini_path = tmp_path / "profiles.ini"
    ini_path.write_text("[General]\nStartWithLastProfile=1\n", encoding="utf-8")
    monkeypatch.setattr(browser_cookie_import, "_firefox_profiles_ini_path", lambda: str(ini_path))

    assert FirefoxCookieImporter().list_profiles() == []
