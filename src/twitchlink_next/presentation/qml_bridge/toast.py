"""Toast notifications, exposed to QML as a singleton.

Python only announces "a toast was requested" — the transient on-screen
list (auto-dismiss timers, stacking, animation) is owned by
``ToastHost.qml``. A toast's lifetime is a pure presentation concern with
no business meaning, so it doesn't need to live in a Python-held model.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtQml import QmlElement, QmlSingleton

QML_IMPORT_NAME = "TwitchLinkNext"
QML_IMPORT_MAJOR_VERSION = 1


@QmlElement
@QmlSingleton
class ToastController(QObject):
    toastRequested = Signal(str, str)  # message, kind ("info" | "success" | "error")

    @Slot(str)
    def info(self, message: str) -> None:
        self.toastRequested.emit(message, "info")

    @Slot(str)
    def success(self, message: str) -> None:
        self.toastRequested.emit(message, "success")

    @Slot(str)
    def error(self, message: str) -> None:
        self.toastRequested.emit(message, "error")
