"""Entry point.

Mirrors TwitchLink 3.5.5's ``TwitchLink.py`` in shape (one function that
starts the app), but with no import-time side effects: nothing runs until
``main()`` is called, and ``main()`` builds every dependency explicitly
instead of importing a ready-made global ``App.Instance``.
"""

from __future__ import annotations

import sys

from PySide6.QtGui import QGuiApplication

from twick_hub.bootstrap.application import Application
from twick_hub.bootstrap.dependencies import build_container


def main() -> int:
    container = build_container()
    qt_app = QGuiApplication(sys.argv)
    app = Application(container, qt_app)
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
