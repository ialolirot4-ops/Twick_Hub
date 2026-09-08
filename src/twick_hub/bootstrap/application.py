"""Owns process lifecycle: the Qt application object, the Qt+asyncio event
loop bridge, the QML engine, startup and shutdown.

``Application`` takes an already-constructed ``QGuiApplication`` rather
than creating one itself: Qt allows exactly one ``QGuiApplication`` per
process (confirmed empirically — a second construction raises
``RuntimeError`` from shiboken), so ownership belongs to whoever manages
that process-wide lifetime. ``main()`` constructs it once for a real run;
tests inject pytest-qt's session-scoped ``qapp`` fixture instead of each
creating their own. Either way, it replaces TwitchLink 3.5.5's
``Core/App.py`` singleton (docs/architecture-decisions.md AD-03): the
``Application`` object here is built explicitly, not created as an
import-time side effect, and callers never reach it through a global —
they have it because it was handed to them.

Qt + asyncio integration uses ``qasync`` (docs/architecture-decisions.md
stack list already includes ``asyncio where fitting`` alongside PySide6;
qasync is the standard, minimal bridge between Qt's event loop and
asyncio's — writing that bridge by hand is exactly the kind of fragile
infrastructure code a well-established, small, widely-used library solves
correctly). The pattern below (an ``asyncio.Event`` set by Qt's
``aboutToQuit`` signal) is qasync's own documented way to run a GUI app's
event loop to completion.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path

import qasync
from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from twick_hub.bootstrap.container import Container
from twick_hub.presentation import (
    qml_bridge,  # noqa: F401  (registers QML singletons on import)
)

logger = logging.getLogger(__name__)

_QML_MAIN = Path(__file__).resolve().parents[1] / "presentation" / "qml" / "Main.qml"


class Application:
    def __init__(self, container: Container, qt_app: QGuiApplication) -> None:
        self._container = container
        self.qt_app = qt_app
        self.qml_engine: QQmlApplicationEngine | None = None

    def run(self, *, on_started: Callable[[], None] | None = None) -> int:
        """Loads the QML shell and blocks until the app quits.

        ``on_started`` is an optional hook invoked right after the QML
        shell has loaded successfully, before the event loop blocks. FASE 1
        has no real UI to trigger a quit from, so tests use this hook to
        schedule one — see tests/test_application_lifecycle.py. Production
        code (``main.py``) calls ``run()`` with no argument.
        """
        loop = qasync.QEventLoop(self.qt_app)
        asyncio.set_event_loop(loop)

        close_event = asyncio.Event()
        self.qt_app.aboutToQuit.connect(close_event.set)

        self.qml_engine = QQmlApplicationEngine()
        self.qml_engine.load(QUrl.fromLocalFile(str(_QML_MAIN)))
        if not self.qml_engine.rootObjects():
            logger.error("QML failed to load from %s", _QML_MAIN)
            return 1

        logger.info("%s skeleton started.", self._container.config.app_name)
        if on_started is not None:
            on_started()

        try:
            with loop:
                loop.run_until_complete(close_event.wait())
        finally:
            self._shutdown()
        return 0

    def _shutdown(self) -> None:
        logger.info("Shutting down.")
        if self.qml_engine is not None:
            self.qml_engine.deleteLater()
        self._container.engine.dispose()
