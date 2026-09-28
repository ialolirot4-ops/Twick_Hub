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

import qasync
from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from twick_hub.bootstrap.container import Container
from twick_hub.bootstrap.runtime_paths import package_root
from twick_hub.presentation import (
    qml_bridge,  # noqa: F401  (registers QML singletons on import)
)
from twick_hub.presentation.qml_bridge.context import Bridges, install_bridges
from twick_hub.presentation.qml_bridge.tasks import TaskRunner

logger = logging.getLogger(__name__)

# FASE 19: computed via runtime_paths.package_root(), not a bare
# ``Path(__file__)`` walk — see that module's docstring for why a frozen
# (PyInstaller) build needs a different base path than a source run.
_QML_MAIN = package_root() / "presentation" / "qml" / "Main.qml"


class Application:
    def __init__(self, container: Container, qt_app: QGuiApplication) -> None:
        self._container = container
        self.qt_app = qt_app
        self.qml_engine: QQmlApplicationEngine | None = None
        self.bridges: Bridges | None = None  # keeps the QML data models alive
        self._tasks: TaskRunner | None = None  # the UI's in-flight tasks, cancelled at shutdown

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
        # FASE 21b: the data bridges must be on the root context *before*
        # the QML loads, or the pages' bindings would hit undefined names.
        self._tasks = TaskRunner(loop.create_task)
        self.bridges = install_bridges(self.qml_engine, self._container, self._tasks)
        self.qml_engine.load(QUrl.fromLocalFile(str(_QML_MAIN)))
        if not self.qml_engine.rootObjects():
            logger.error("QML failed to load from %s", _QML_MAIN)
            # Same teardown as a normal exit: nothing has run yet, but the
            # loop must still be closed and the container's resources released.
            with loop:
                self._close_resources(loop)
            self._shutdown()
            return 1

        logger.info("%s started.", self._container.config.app_name)
        if on_started is not None:
            on_started()

        try:
            with loop:
                try:
                    loop.run_until_complete(close_event.wait())
                finally:
                    # Still inside the loop: workers and HTTP clients are
                    # async resources and must be closed on the loop that
                    # ran them, before it is closed (FASE 22.1, AD-103).
                    self._close_resources(loop)
        finally:
            self._shutdown()
        return 0

    def _close_resources(self, loop: asyncio.AbstractEventLoop) -> None:
        try:
            loop.run_until_complete(self._aclose_resources())
        except Exception:  # noqa: BLE001 - shutdown must still reach engine.dispose()
            logger.exception("Error while closing resources.")

    async def _aclose_resources(self) -> None:
        # The UI's tasks first (they use what the container closes next),
        # then each of the container's closers in order. One failing closer
        # is logged and never stops the next one.
        if self._tasks is not None:
            await self._tasks.cancel_all()
        for close in self._container.closers:
            try:
                await close()
            except Exception:  # noqa: BLE001 - see above
                logger.exception("A resource failed to close; continuing shutdown.")

    def _shutdown(self) -> None:
        logger.info("Shutting down.")
        if self.qml_engine is not None:
            self.qml_engine.deleteLater()
        self._container.engine.dispose()
