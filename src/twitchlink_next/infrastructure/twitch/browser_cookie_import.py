"""Browser cookie import — obtains the user's Twitch session token by
reading it out of their own, already-logged-in Firefox profile.

Ported from TwitchLink 3.5.5's ``Services/Account/BrowserCookieDetector``
(docs/migration-map.md: only a Firefox detector exists there — no Chrome
support either, a limitation this port keeps rather than silently
expanding scope). ``selenium`` is imported inside the methods that need
it, not at module level, per docs/architecture-decisions.md AD-08 — this
whole module can be imported (e.g. to check ``is_available()``) without
paying for selenium's import cost until a user actually tries to connect
this way.

**Verification status (honest, not assumed):** this cannot be exercised
in the sandbox this phase was built in — there is no Firefox, no
geckodriver, and no real Twitch account to log into here. The shape is
ported faithfully from working code (docs/migration-map.md classifies
the source as RIESGO, not INCORRECTO), but hasn't been re-verified
end-to-end for this port. Confirm on a real desktop before relying on it.
"""

from __future__ import annotations

import configparser
import os
import sys
from dataclasses import dataclass
from typing import Protocol

from twitchlink_next.infrastructure.twitch.errors import NoBrowserSessionFoundError

_TWITCH_URL = "https://www.twitch.tv"
_TWITCH_DOMAIN = ".twitch.tv"
_AUTH_COOKIE_NAME = "auth-token"


@dataclass(frozen=True, slots=True)
class BrowserProfile:
    key: str
    display_name: str


class CookieImporter(Protocol):
    """What ``TwitchAccountService`` actually depends on — not the
    concrete ``FirefoxCookieImporter``, so tests can substitute a fake
    without a real browser, and a future Chrome/Chromium importer
    (docs/architecture-decisions.md AD-08) can be swapped in the same way.
    """

    def list_profiles(self) -> list[BrowserProfile]: ...

    def import_session_token(self, profile: BrowserProfile) -> str: ...


def _firefox_profiles_ini_path() -> str:
    if sys.platform == "win32":
        return os.path.expandvars(r"%APPDATA%\Mozilla\Firefox\profiles.ini")
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/Firefox/profiles.ini")
    return os.path.expanduser("~/.mozilla/firefox/profiles.ini")


def _firefox_user_data_path() -> str:
    if sys.platform == "win32":
        return os.path.expandvars(r"%APPDATA%\Mozilla\Firefox")
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/Firefox")
    return os.path.expanduser("~/.mozilla/firefox")


class FirefoxCookieImporter:
    def list_profiles(self) -> list[BrowserProfile]:
        parser = configparser.ConfigParser()
        try:
            read_files = parser.read(_firefox_profiles_ini_path(), encoding="utf-8")
        except configparser.Error as error:
            raise NoBrowserSessionFoundError(
                f"Couldn't read Firefox's profiles.ini: {error}"
            ) from error

        if not read_files:
            raise NoBrowserSessionFoundError(
                "Firefox doesn't appear to be installed for this user."
            )

        return [
            BrowserProfile(
                key=parser.get(section, "Path", fallback=""),
                display_name=parser.get(section, "Name", fallback=section),
            )
            for section in parser.sections()
            if section.lower().startswith("profile")
        ]

    def import_session_token(self, profile: BrowserProfile) -> str:
        """Launches a headless Firefox bound to ``profile``'s real data
        directory, visits twitch.tv, and reads the ``auth-token`` cookie
        Twitch itself set there when the user logged in through their
        actual browser.
        """
        # Imported here, not at module level — see this module's docstring.
        import selenium.webdriver

        options = selenium.webdriver.FirefoxOptions()
        options.profile = selenium.webdriver.FirefoxProfile(  # type: ignore[attr-defined]
            os.path.join(_firefox_user_data_path(), profile.key)
        )
        options.add_argument("-headless")

        try:
            driver = selenium.webdriver.Firefox(options=options)
        except Exception as error:
            raise NoBrowserSessionFoundError(
                f"Couldn't start Firefox for cookie import: {error}"
            ) from error

        try:
            driver.get(_TWITCH_URL)
            for cookie in driver.get_cookies():
                is_twitch = cookie.get("domain") == _TWITCH_DOMAIN
                is_auth_cookie = cookie.get("name") == _AUTH_COOKIE_NAME
                if is_twitch and is_auth_cookie:
                    return cookie["value"]
        finally:
            driver.quit()

        raise NoBrowserSessionFoundError(
            "No Twitch session found in this Firefox profile — log in to twitch.tv in "
            "Firefox first, then try again."
        )
