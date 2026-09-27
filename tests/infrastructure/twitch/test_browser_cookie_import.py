from __future__ import annotations

import sys
import textwrap

import pytest
import selenium.webdriver

import twick_hub.infrastructure.twitch.browser_cookie_import as browser_cookie_import
from twick_hub.infrastructure.twitch.browser_cookie_import import (
    BrowserProfile,
    FirefoxCookieImporter,
)
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


# FASE 17 — Security + Hardening: a malicious/tampered profiles.ini must not
# be able to point the (real, launched) Firefox process at a directory
# outside Firefox's own user-data folder via a "../.." profile key. This is
# checked, and must raise, before selenium is even imported — so this test
# does not require selenium/geckodriver/a real Firefox to be installed.


@pytest.mark.parametrize(
    "malicious_key",
    [
        "../../../../etc",
        "/etc/passwd",
        # A "..\\..\\Windows\\System32"-style key is the Windows-relevant
        # traversal shape, but ``\\`` is only a path separator when
        # ``os.sep == "\\"`` — on this (Linux) test platform it's just a
        # literal character in one path component, so it wouldn't exercise
        # the guard at all here and would instead fail for an unrelated
        # reason (selenium trying and failing to copy a directory with a
        # literal backslash in its name). Covered by the two POSIX-style
        # cases above, which are meaningful on every platform this runs on.
    ],
)
def test_import_session_token_rejects_profile_path_escaping_user_data_dir(
    tmp_path, monkeypatch, malicious_key
):
    user_data_dir = tmp_path / "Firefox"
    user_data_dir.mkdir()
    monkeypatch.setattr(
        browser_cookie_import, "_firefox_user_data_path", lambda: str(user_data_dir)
    )

    importer = FirefoxCookieImporter()
    profile = BrowserProfile(key=malicious_key, display_name="evil")

    with pytest.raises(NoBrowserSessionFoundError, match="outside its user-data directory"):
        importer.import_session_token(profile)


def test_import_session_token_accepts_a_profile_key_inside_user_data_dir(tmp_path, monkeypatch):
    """Doesn't (and can't, without a real browser) verify the successful
    cookie-import path end to end — only that a *legitimate* relative
    profile key is not rejected by the new path-traversal guard itself,
    i.e. the guard doesn't false-positive on ordinary input. Whatever
    happens next (selenium not installed here, or a real webdriver failing
    to start with no display/browser available) is fine and expected in
    this sandbox — the only thing this test pins down is that it is NOT
    the guard's own rejection."""
    user_data_dir = tmp_path / "Firefox"
    profile_dir = user_data_dir / "xxxxxxxx.default"
    profile_dir.mkdir(parents=True)
    monkeypatch.setattr(
        browser_cookie_import, "_firefox_user_data_path", lambda: str(user_data_dir)
    )

    importer = FirefoxCookieImporter()
    profile = BrowserProfile(key="xxxxxxxx.default", display_name="default")

    try:
        importer.import_session_token(profile)
    except NoBrowserSessionFoundError as error:
        assert "outside its user-data directory" not in str(error)
    except ModuleNotFoundError as error:
        assert "selenium" in str(error)  # no selenium installed in this sandbox — expected


# FASE 18 — Testing: everything below closes gaps found by measuring
# coverage against the real suite (docs/phase-state.md) — the
# platform-specific path branches (only whichever one matches this
# sandbox's actual platform was ever exercised before), the malformed-ini
# error path, and — the biggest one — the actual driver interaction inside
# ``import_session_token``, which had no coverage beyond the path-traversal
# guard that runs before it. ``selenium`` genuinely is installed in this
# sandbox (unlike what the comment above assumed when this file was first
# written — there's simply no real Firefox/geckodriver binary for it to
# launch), so ``selenium.webdriver.Firefox`` — the one call that actually
# needs a real browser — can be monkeypatched to a fake driver, exactly
# like any other injected dependency, without faking anything Selenium
# itself does.


@pytest.mark.parametrize(
    ("platform", "expected_fragment"),
    [
        ("win32", "Mozilla\\Firefox\\profiles.ini"),
        ("darwin", "Library/Application Support/Firefox/profiles.ini"),
        ("linux", ".mozilla/firefox/profiles.ini"),
    ],
)
def test_firefox_profiles_ini_path_is_platform_specific(monkeypatch, platform, expected_fragment):
    monkeypatch.setattr(sys, "platform", platform)
    assert expected_fragment in browser_cookie_import._firefox_profiles_ini_path()


@pytest.mark.parametrize(
    ("platform", "expected_fragment"),
    [
        ("win32", "Mozilla\\Firefox"),
        ("darwin", "Library/Application Support/Firefox"),
        ("linux", ".mozilla/firefox"),
    ],
)
def test_firefox_user_data_path_is_platform_specific(monkeypatch, platform, expected_fragment):
    monkeypatch.setattr(sys, "platform", platform)
    assert expected_fragment in browser_cookie_import._firefox_user_data_path()


def test_list_profiles_with_a_malformed_ini_raises(tmp_path, monkeypatch):
    ini_path = tmp_path / "profiles.ini"
    ini_path.write_text("this is not valid ini syntax at all\n[", encoding="utf-8")
    monkeypatch.setattr(browser_cookie_import, "_firefox_profiles_ini_path", lambda: str(ini_path))

    with pytest.raises(NoBrowserSessionFoundError, match="Couldn't read Firefox's profiles.ini"):
        FirefoxCookieImporter().list_profiles()


class _FakeSeleniumDriver:
    def __init__(self, cookies: list[dict]) -> None:
        self._cookies = cookies
        self.visited_url: str | None = None
        self.quit_called = False

    def get(self, url: str) -> None:
        self.visited_url = url

    def get_cookies(self) -> list[dict]:
        return self._cookies

    def quit(self) -> None:
        self.quit_called = True


def _real_profile_dir(tmp_path, monkeypatch) -> BrowserProfile:
    user_data_dir = tmp_path / "Firefox"
    profile_dir = user_data_dir / "xxxxxxxx.default"
    profile_dir.mkdir(parents=True)
    monkeypatch.setattr(
        browser_cookie_import, "_firefox_user_data_path", lambda: str(user_data_dir)
    )
    return BrowserProfile(key="xxxxxxxx.default", display_name="default")


def test_import_session_token_returns_the_twitch_auth_cookie(tmp_path, monkeypatch):
    profile = _real_profile_dir(tmp_path, monkeypatch)
    driver = _FakeSeleniumDriver(
        cookies=[
            {"domain": ".other.example", "name": "auth-token", "value": "not-this-one"},
            {"domain": ".twitch.tv", "name": "auth-token", "value": "the-real-token"},
        ]
    )
    monkeypatch.setattr(selenium.webdriver, "Firefox", lambda options: driver)

    result = FirefoxCookieImporter().import_session_token(profile)

    assert result == "the-real-token"
    assert driver.visited_url == "https://www.twitch.tv"
    assert driver.quit_called is True


def test_import_session_token_raises_when_no_twitch_cookie_is_present(tmp_path, monkeypatch):
    profile = _real_profile_dir(tmp_path, monkeypatch)
    driver = _FakeSeleniumDriver(
        cookies=[{"domain": ".other.example", "name": "auth-token", "value": "x"}]
    )
    monkeypatch.setattr(selenium.webdriver, "Firefox", lambda options: driver)

    with pytest.raises(NoBrowserSessionFoundError, match="No Twitch session found"):
        FirefoxCookieImporter().import_session_token(profile)

    assert driver.quit_called is True  # quit() runs even when nothing was found


def test_import_session_token_wraps_a_webdriver_launch_failure(tmp_path, monkeypatch):
    profile = _real_profile_dir(tmp_path, monkeypatch)

    def _boom(options):
        raise OSError("geckodriver not found on PATH")

    monkeypatch.setattr(selenium.webdriver, "Firefox", _boom)

    with pytest.raises(NoBrowserSessionFoundError, match="Couldn't start Firefox"):
        FirefoxCookieImporter().import_session_token(profile)
