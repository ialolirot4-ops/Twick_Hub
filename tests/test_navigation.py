from typing import cast

from twick_hub.presentation.qml_bridge.navigation import NavigationController


def test_starts_on_home(qapp):
    nav = NavigationController()
    assert nav.currentPageId == "home"
    assert nav.currentPageSource == "pages/HomePage.qml"


def test_exposes_all_eleven_pages_in_sidebar_order(qapp):
    nav = NavigationController()
    # PySide6's stub doesn't propagate the getter's return type for a
    # Property declared with a bare container type (list); the value is a
    # real list[dict[str, str]] at runtime (verified) — cast() documents
    # that rather than silencing the checker with a bare ignore.
    pages = cast("list[dict[str, str]]", nav.pages)
    ids = [page["id"] for page in pages]
    assert ids == [
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


def test_navigate_changes_current_page_and_emits(qapp):
    nav = NavigationController()
    seen = []
    nav.currentPageIdChanged.connect(lambda: seen.append(nav.currentPageId))

    nav.navigate("settings")

    assert nav.currentPageId == "settings"
    assert nav.currentPageSource == "pages/SettingsPage.qml"
    assert seen == ["settings"]


def test_navigate_to_unknown_id_is_ignored(qapp):
    """A typo'd or stale page id must never leave the shell on a broken
    page — silently ignoring it (and not emitting) is the safe default."""
    nav = NavigationController()
    seen = []
    nav.currentPageIdChanged.connect(lambda: seen.append(nav.currentPageId))

    nav.navigate("does-not-exist")

    assert nav.currentPageId == "home"
    assert seen == []


def test_navigate_to_current_page_is_a_no_op(qapp):
    nav = NavigationController()
    seen = []
    nav.currentPageIdChanged.connect(lambda: seen.append(True))

    nav.navigate("home")

    assert seen == []
