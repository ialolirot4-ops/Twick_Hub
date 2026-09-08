"""Proves the skeleton opens and closes cleanly — the core requirement of
the FASE 1 gate ("Debe: abrir; cerrar; inicializar dependencias; ...").
"""

from __future__ import annotations

from PySide6.QtCore import QTimer

from twick_hub.bootstrap.application import Application
from twick_hub.bootstrap.container import Container

# `qapp` comes from pytest-qt: one QGuiApplication for the whole test
# session. Qt allows exactly one per process, so Application takes it as
# a constructor argument instead of building its own — see
# bootstrap/application.py's module docstring for why.


def test_application_opens_and_closes_cleanly(container: Container, qapp):
    app = Application(container, qapp)

    def _quit_shortly() -> None:
        # Mirrors what happens when a user closes the window: Qt's
        # aboutToQuit fires either way, which is what Application.run()
        # actually waits on.
        QTimer.singleShot(50, qapp.quit)

    exit_code = app.run(on_started=_quit_shortly)

    assert exit_code == 0
    assert app.qml_engine is not None
    assert len(app.qml_engine.rootObjects()) >= 1


def test_application_reports_failure_if_qml_is_missing(container: Container, qapp, monkeypatch):
    import twick_hub.bootstrap.application as application_module

    monkeypatch.setattr(
        application_module, "_QML_MAIN", application_module._QML_MAIN.parent / "DoesNotExist.qml"
    )

    app = Application(container, qapp)
    exit_code = app.run(on_started=lambda: None)

    assert exit_code == 1
