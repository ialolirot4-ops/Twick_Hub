"""Attaches the data bridges to one QML engine (FASE 21b).

Dependency injection for QML: each bridge is a plain Python object built
from the ``Container``'s services and exposed to *that engine's* root
context under a fixed name. No module-level state, no singleton — the
same pattern as ``Application`` receiving its ``Container``: whoever
builds the engine decides what it gets (AD-03). ``NavigationController``,
``Theme`` and ``ToastController`` stay ``@QmlSingleton`` — they hold no
application data, so they need no injection.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtQml import QQmlEngine

from twick_hub.bootstrap.container import Container
from twick_hub.presentation.qml_bridge.downloads_model import DownloadsModel
from twick_hub.presentation.qml_bridge.favorites_model import FavoritesModel
from twick_hub.presentation.qml_bridge.history_model import HistoryModel
from twick_hub.presentation.qml_bridge.tasks import TaskRunner


@dataclass(frozen=True, slots=True)
class Bridges:
    """References to the bridge objects. They are owned by the engine (Qt
    parent); this just gives Python callers typed access."""

    favorites: FavoritesModel
    downloads: DownloadsModel
    history: HistoryModel


def install_bridges(engine: QQmlEngine, container: Container, runner: TaskRunner) -> Bridges:
    # Parented to the engine so Qt destroys them *after* the engine has torn
    # down the QML that binds to them — otherwise a page still alive at exit
    # reads a deleted model and logs "Cannot read property of null".
    bridges = Bridges(
        favorites=FavoritesModel(
            container.favorites, container.platform_registry, runner, parent=engine
        ),
        downloads=DownloadsModel(
            container.downloads, container.download_service, runner, parent=engine
        ),
        history=HistoryModel(container.downloads, runner, parent=engine),
    )
    context = engine.rootContext()
    context.setContextProperty("favoritesModel", bridges.favorites)
    context.setContextProperty("downloadsModel", bridges.downloads)
    context.setContextProperty("historyModel", bridges.history)
    return bridges
