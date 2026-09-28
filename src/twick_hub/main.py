"""Entry point.

Mirrors TwitchLink 3.5.5's ``TwitchLink.py`` in shape (one function that
starts the app), but with no import-time side effects: nothing runs until
``main()`` is called, and ``main()`` builds every dependency explicitly
instead of importing a ready-made global ``App.Instance``.
"""

from __future__ import annotations

import sys

from PySide6.QtGui import QGuiApplication
from PySide6.QtNetwork import QNetworkAccessManager

from twick_hub.bootstrap.application import Application
from twick_hub.bootstrap.dependencies import build_container
from twick_hub.bootstrap.migrations import ensure_schema_migrated
from twick_hub.bootstrap.platforms import build_platform_adapters
from twick_hub.config.settings import load_config


def main() -> int:
    config = load_config()
    # FASE 21c: the Qt app comes first — Twitch's IntegrityAdapter is a
    # QObject and needs a QNetworkAccessManager — then the real platform
    # adapters, then the (Qt-free) container that holds them.
    qt_app = QGuiApplication(sys.argv)
    platform_adapters = build_platform_adapters(config, network_manager=QNetworkAccessManager())
    container = build_container(config, platform_adapters=platform_adapters)
    ensure_schema_migrated(container.engine)  # RISK-PKG-02: create/upgrade the schema
    app = Application(container, qt_app)
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
