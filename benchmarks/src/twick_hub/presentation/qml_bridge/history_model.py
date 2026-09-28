"""History page bridge (FASE 21b): finished downloads (completed, failed,
cancelled) from the real ``SqlDownloadRepository``, newest first.
``openFolder`` reveals a download's directory through an injectable opener
so tests never launch a real file manager.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Slot
from PySide6.QtGui import QDesktopServices

from twick_hub.application.downloads import ListDownloadHistoryUseCase
from twick_hub.domain.downloads import Download
from twick_hub.domain.enums import DownloadStatus
from twick_hub.domain.protocols import DownloadRepository
from twick_hub.presentation.qml_bridge.row_model import Row, RowListModel
from twick_hub.presentation.qml_bridge.tasks import TaskRunner


def _open_with_desktop(folder: Path) -> bool:
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))


def format_size(size_bytes: int | None) -> str:
    if size_bytes is None:
        return "—"
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"  # unreachable; keeps the type checker satisfied


def _row(download: Download) -> Row:
    when = download.completed_at or download.created_at
    finished_ok = download.status is DownloadStatus.COMPLETED
    return {
        "id": download.id,
        "title": download.media.title,
        "platform": download.media.ref.platform.value,
        "date": f"{when:%b} {when.day}, {when.year}",
        "size": format_size(download.file_size_bytes) if finished_ok else "",
        # Only non-success outcomes get a label; a completed row shows its size.
        "outcome": "" if finished_ok else download.status.value.capitalize(),
        "errorMessage": download.error_message or "",
    }


class HistoryModel(RowListModel):
    ROLES = ("id", "title", "platform", "date", "size", "outcome", "errorMessage")

    def __init__(
        self,
        downloads: DownloadRepository,
        runner: TaskRunner,
        opener: Callable[[Path], bool] = _open_with_desktop,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(self.ROLES, parent)
        self._list = ListDownloadHistoryUseCase(downloads)
        self._runner = runner
        self._opener = opener
        self._destinations: dict[str, str] = {}

    @Slot()
    def refresh(self) -> None:
        self._runner.run(self.reload())

    async def reload(self) -> None:
        downloads = await self._list.execute()
        self._destinations = {d.id: d.destination_path for d in downloads}
        self.replace_rows([_row(d) for d in downloads])

    @Slot(str, result=bool)
    def openFolder(self, download_id: str) -> bool:  # noqa: N802 (Qt slot)
        destination = self._destinations.get(download_id)
        if destination is None:
            return False
        folder = Path(destination).parent
        return folder.is_dir() and self._opener(folder)
