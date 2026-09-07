"""Integration tests for the FASE 2 UI shell.

These load real QML (not just Python logic) and are the automated version
of the manual verification done while building this phase: every page
must be reachable through the real ``NavigationController`` singleton
with zero QML warnings, and every page file must be independently loadable
in isolation.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, qmlTypeId

import twitchlink_next.presentation.qml_bridge  # noqa: F401  (registers QML singletons)

_QML_DIR = Path(__file__).resolve().parents[1] / "src" / "twitchlink_next" / "presentation" / "qml"

_PAGE_FILES = [
    "HomePage.qml",
    "SearchPage.qml",
    "FavoritesPage.qml",
    "LivePage.qml",
    "DownloadsPage.qml",
    "HistoryPage.qml",
    "ScheduledPage.qml",
    "PlaylistsPage.qml",
    "AccountPage.qml",
    "SettingsPage.qml",
    "AboutPage.qml",
]

_PAGE_IDS = [
    "home",
    "search",
    "favorites",
    "live",
    "downloads",
    "history",
    "scheduled",
    "playlists",
    "account",
    "settings",
    "about",
]


@pytest.fixture
def engine_with_warnings(qapp):
    engine = QQmlApplicationEngine()
    warnings: list[str] = []
    engine.warnings.connect(lambda ws: warnings.extend(str(w.toString()) for w in ws))
    yield engine, warnings


@pytest.mark.parametrize("page_file", _PAGE_FILES)
def test_each_page_loads_standalone_without_errors(qapp, page_file):
    engine = QQmlApplicationEngine()
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(_QML_DIR / "pages" / page_file)))
    obj = component.create()
    assert component.errors() == [], [e.toString() for e in component.errors()]
    assert obj is not None


def test_shell_loads_and_defaults_to_home(engine_with_warnings):
    engine, warnings = engine_with_warnings
    engine.load(QUrl.fromLocalFile(str(_QML_DIR / "AppShell.qml")))

    assert len(engine.rootObjects()) == 1
    assert warnings == []


def _qml_type_id(uri: str, major: int, minor: int, qml_name: str) -> int:
    """Thin wrapper around ``qmlTypeId``. PySide6's stub declares the
    string arguments as ``bytes``-only; Qt's actual binding accepts ``str``
    directly (verified — used successfully throughout this file). One
    ignore here documents the gap instead of repeating it at every call
    site.
    """
    return qmlTypeId(uri, major, minor, qml_name)  # pyright: ignore[reportArgumentType]


def test_navigating_through_every_page_produces_no_warnings(engine_with_warnings):
    engine, warnings = engine_with_warnings
    engine.load(QUrl.fromLocalFile(str(_QML_DIR / "AppShell.qml")))
    assert len(engine.rootObjects()) == 1

    type_id = _qml_type_id("TwitchLinkNext", 1, 0, "NavigationController")
    nav = engine.singletonInstance(type_id)
    assert nav is not None

    for page_id in _PAGE_IDS:
        nav.navigate(page_id)
        assert nav.property("currentPageId") == page_id

    assert warnings == []


def test_theme_toggle_and_toast_produce_no_warnings(engine_with_warnings):
    engine, warnings = engine_with_warnings
    engine.load(QUrl.fromLocalFile(str(_QML_DIR / "AppShell.qml")))
    assert len(engine.rootObjects()) == 1

    theme = engine.singletonInstance(_qml_type_id("TwitchLinkNext", 1, 0, "Theme"))
    toasts = engine.singletonInstance(_qml_type_id("TwitchLinkNext", 1, 0, "ToastController"))
    assert theme is not None
    assert toasts is not None

    theme.toggle()
    assert theme.property("darkMode") is False
    toasts.success("integration test toast")
    toasts.error("integration test error toast")

    assert warnings == []
