"""Navigation controller, exposed to QML as a singleton.

Holds the sidebar's page list and which one is current. Page content is
still entirely mocked (Master Plan §36: "No conectar plataformas reales") —
this only owns *which screen is showing*, not any real data.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QObject, Signal, Slot
from PySide6.QtQml import QmlElement, QmlSingleton

QML_IMPORT_NAME = "TwitchLinkNext"
QML_IMPORT_MAJOR_VERSION = 1

# (id, label, source file under presentation/qml/pages/). Order here is the
# sidebar's order. A plain list of dicts is enough for eleven static
# entries — a real QAbstractListModel is worth its complexity once a list
# is dynamic (FASE 9 Favorites, FASE 10 Live, etc. will need one).
_PAGES: list[dict[str, str]] = [
    {"id": "home", "label": "Home", "source": "pages/HomePage.qml"},
    {"id": "search", "label": "Search", "source": "pages/SearchPage.qml"},
    {"id": "favorites", "label": "Favorites", "source": "pages/FavoritesPage.qml"},
    {"id": "live", "label": "Live", "source": "pages/LivePage.qml"},
    {"id": "downloads", "label": "Downloads", "source": "pages/DownloadsPage.qml"},
    {"id": "history", "label": "History", "source": "pages/HistoryPage.qml"},
    {"id": "scheduled", "label": "Scheduled", "source": "pages/ScheduledPage.qml"},
    {"id": "playlists", "label": "Playlists", "source": "pages/PlaylistsPage.qml"},
    {"id": "account", "label": "Account", "source": "pages/AccountPage.qml"},
    {"id": "settings", "label": "Settings", "source": "pages/SettingsPage.qml"},
    {"id": "about", "label": "About", "source": "pages/AboutPage.qml"},
]

_VALID_IDS = {page["id"] for page in _PAGES}


@QmlElement
@QmlSingleton
class NavigationController(QObject):
    currentPageIdChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._current_page_id = "home"

    @Property(list, constant=True)
    def pages(self) -> list[dict[str, str]]:
        return _PAGES

    def _get_current_page_id(self) -> str:
        return self._current_page_id

    currentPageId = Property(str, _get_current_page_id, notify=currentPageIdChanged)

    @Property(str, notify=currentPageIdChanged)
    def currentPageSource(self) -> str:
        for page in _PAGES:
            if page["id"] == self._current_page_id:
                return page["source"]
        return _PAGES[0]["source"]

    @Slot(str)
    def navigate(self, page_id: str) -> None:
        if page_id in _VALID_IDS and page_id != self._current_page_id:
            self._current_page_id = page_id
            self.currentPageIdChanged.emit()
