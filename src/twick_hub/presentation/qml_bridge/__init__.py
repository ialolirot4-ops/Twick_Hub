"""Importing this package registers every ``@QmlElement`` type it contains
(Theme, NavigationController, ToastController) with the QML engine's type
system. ``bootstrap/application.py`` imports this before loading any QML —
see its module docstring.
"""

from __future__ import annotations

from twick_hub.presentation.qml_bridge import navigation, theme, toast

__all__ = ["navigation", "theme", "toast"]
