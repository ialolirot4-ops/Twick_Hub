"""A small dict-row list model shared by the FASE 21b bridges.

Each bridge (favorites, downloads, history) is a flat list of rows shown
by one QML ``Repeater``. Rather than three near-identical
``QAbstractListModel`` subclasses, they share this one: rows are plain
dicts keyed by role name, and ``replace_rows`` diffs against the current
rows so a progress tick emits ``dataChanged`` for the affected rows
instead of resetting the whole list (which would rebuild every delegate
once a second).

Not registered with QML (``@QmlElement``): instances are created in
Python, handed the ``Container``-derived dependencies explicitly, and
attached to one engine's root context by ``qml_bridge/context.py`` — never
through a module-level global (AD-03).
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QObject,
    Qt,
    Signal,
)

Row = dict[str, Any]


class RowListModel(QAbstractListModel):
    countChanged = Signal()
    loadedChanged = Signal()

    def __init__(self, roles: tuple[str, ...], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._roles = roles
        self._role_ids = {Qt.ItemDataRole.UserRole + 1 + i: name for i, name in enumerate(roles)}
        self._rows: list[Row] = []
        self._loaded = False

    # --- QAbstractListModel ---------------------------------------------
    def rowCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802 (Qt API)
        if parent is not None and parent.isValid():
            return 0
        return len(self._rows)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        name = self._role_ids.get(role)
        return self._rows[index.row()].get(name) if name is not None else None

    def roleNames(self) -> dict[int, QByteArray]:  # noqa: N802 (Qt API)
        return {role: QByteArray(name.encode()) for role, name in self._role_ids.items()}

    # --- QML-facing state -------------------------------------------------
    @Property(int, notify=countChanged)
    def count(self) -> int:
        return len(self._rows)

    @Property(bool, notify=loadedChanged)
    def loaded(self) -> bool:
        """False until the first load finishes — lets a page show nothing
        (instead of a flash of \"empty\") while the first query runs."""
        return self._loaded

    # --- Python-facing updates ---------------------------------------------
    def rows(self) -> list[Row]:
        return list(self._rows)

    def replace_rows(self, new_rows: list[Row]) -> None:
        if not self._loaded:
            self._loaded = True
            self.loadedChanged.emit()

        same_shape = len(new_rows) == len(self._rows) and all(
            old.get("id") == new.get("id") for old, new in zip(self._rows, new_rows, strict=True)
        )
        if same_shape:
            for row_number, (old, new) in enumerate(zip(self._rows, new_rows, strict=True)):
                if old != new:
                    self._rows[row_number] = new
                    index = self.index(row_number)
                    self.dataChanged.emit(index, index)
            return

        previous_count = len(self._rows)
        self.beginResetModel()
        self._rows = list(new_rows)
        self.endResetModel()
        if previous_count != len(self._rows):
            self.countChanged.emit()
