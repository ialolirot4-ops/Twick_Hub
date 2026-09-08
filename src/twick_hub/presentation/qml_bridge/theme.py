"""Theme token system, exposed to QML as a singleton.

Deliberately not Twitch's own purple-on-near-black nor Kick's green: the
app's own chrome uses a neutral identity so neither platform visually
dominates the shell (docs/architecture-decisions.md AD-05 already treats
Kick as a first-class platform, not an add-on — the same principle applies
to the UI). Twitch/Kick colors appear only as small per-item badges via
``twitchBadge``/``kickBadge``, never as the shell's own background or accent.

This module (and the rest of ``presentation/qml_bridge``) is the only place
allowed to import PySide6 outside of ``bootstrap/`` — Domain and Application
never import it (Master Plan §37, FASE 3).
"""

from __future__ import annotations

from PySide6.QtCore import Property, QObject, Signal, Slot
from PySide6.QtQml import QmlElement, QmlSingleton

QML_IMPORT_NAME = "TwickHub"
QML_IMPORT_MAJOR_VERSION = 1


@QmlElement
@QmlSingleton
class Theme(QObject):
    darkModeChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._dark_mode = True

    # --- dark/light -----------------------------------------------------
    def _get_dark_mode(self) -> bool:
        return self._dark_mode

    def _set_dark_mode(self, value: bool) -> None:
        if value != self._dark_mode:
            self._dark_mode = value
            self.darkModeChanged.emit()

    darkMode = Property(bool, _get_dark_mode, _set_dark_mode, notify=darkModeChanged)

    @Slot()
    def toggle(self) -> None:
        self._set_dark_mode(not self._dark_mode)

    # --- surfaces ---------------------------------------------------------
    @Property(str, notify=darkModeChanged)
    def background(self) -> str:
        return "#14161B" if self._dark_mode else "#F7F6F3"

    @Property(str, notify=darkModeChanged)
    def surface(self) -> str:
        return "#1C1F26" if self._dark_mode else "#FFFFFF"

    @Property(str, notify=darkModeChanged)
    def surfaceElevated(self) -> str:
        return "#242832" if self._dark_mode else "#FFFFFF"

    @Property(str, notify=darkModeChanged)
    def border(self) -> str:
        return "#2E323C" if self._dark_mode else "#E8E6E1"

    # --- text ---------------------------------------------------------
    @Property(str, notify=darkModeChanged)
    def textPrimary(self) -> str:
        return "#F2F1EF" if self._dark_mode else "#1B1B1D"

    @Property(str, notify=darkModeChanged)
    def textSecondary(self) -> str:
        return "#9A9CA5" if self._dark_mode else "#66646C"

    @Property(str, notify=darkModeChanged)
    def textDisabled(self) -> str:
        return "#5C5F68" if self._dark_mode else "#B4B2AC"

    # --- semantic / accent -----------------------------------------------
    # Amber/gold reads as "archive, collection, curation" — distinct from
    # both Twitch purple and Kick green, so the app's own identity never
    # implies favoritism between the two platforms it supports equally.
    @Property(str, constant=True)
    def accent(self) -> str:
        return "#E8A33D"

    @Property(str, constant=True)
    def accentText(self) -> str:
        return "#1B1B1D"

    @Property(str, constant=True)
    def success(self) -> str:
        return "#3FB558"

    @Property(str, constant=True)
    def danger(self) -> str:
        return "#E5484D"

    @Property(str, constant=True)
    def warning(self) -> str:
        return "#E8A33D"

    # --- platform badges (identification only, never app chrome) ---------
    @Property(str, constant=True)
    def twitchBadge(self) -> str:
        return "#9147FF"

    @Property(str, constant=True)
    def kickBadge(self) -> str:
        return "#53FC18"

    # --- spacing scale -----------------------------------------------
    @Property(int, constant=True)
    def spacingXs(self) -> int:
        return 4

    @Property(int, constant=True)
    def spacingSm(self) -> int:
        return 8

    @Property(int, constant=True)
    def spacingMd(self) -> int:
        return 16

    @Property(int, constant=True)
    def spacingLg(self) -> int:
        return 24

    @Property(int, constant=True)
    def spacingXl(self) -> int:
        return 32

    # --- radius -----------------------------------------------
    @Property(int, constant=True)
    def radiusSm(self) -> int:
        return 6

    @Property(int, constant=True)
    def radiusMd(self) -> int:
        return 10

    # --- typography -----------------------------------------------
    @Property(int, constant=True)
    def fontSizeCaption(self) -> int:
        return 12

    @Property(int, constant=True)
    def fontSizeBody(self) -> int:
        return 14

    @Property(int, constant=True)
    def fontSizeSubheading(self) -> int:
        return 17

    @Property(int, constant=True)
    def fontSizeHeading(self) -> int:
        return 22
