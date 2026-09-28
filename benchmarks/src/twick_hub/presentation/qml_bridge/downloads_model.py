"""Downloads page bridge (FASE 21b): in-flight downloads from the real
``SqlDownloadRepository``, with live progress read from the download
engine.

Progress isn't persisted while a download runs (the executor writes
``progress_percent`` only on completion), so the live number comes from
``DownloadEngine.progress_of`` — an in-memory lookup. The QML page runs a
1 Hz ``Timer`` calling ``refresh()`` only while it is visible *and*
``hasActive`` is true; nothing polls at idle or on other pages.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Property, QObject, Signal, Slot

from twick_hub.application.downloads import CancelDownloadUseCase, ListActiveDownloadsUseCase
from twick_hub.domain.downloads import Download
from twick_hub.domain.enums import DownloadStatus, MediaKind
from twick_hub.domain.protocols import DownloadEngine, DownloadRepository
from twick_hub.presentation.qml_bridge.row_model import Row, RowListModel
from twick_hub.presentation.qml_bridge.tasks import TaskRunner

logger = logging.getLogger(__name__)

_STATUS_LABELS = {
    DownloadStatus.QUEUED: "Queued",
    DownloadStatus.PREPARING: "Preparing",
    DownloadStatus.DOWNLOADING: "Downloading",
    DownloadStatus.PROCESSING: "Processing",
    DownloadStatus.PAUSED: "Paused",
}


class DownloadsModel(RowListModel):
    ROLES = ("id", "title", "platform", "progress", "progressKnown", "statusLabel")

    hasActiveChanged = Signal()

    def __init__(
        self,
        downloads: DownloadRepository,
        engine: DownloadEngine,
        runner: TaskRunner,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(self.ROLES, parent)
        self._list = ListActiveDownloadsUseCase(downloads)
        self._cancel = CancelDownloadUseCase(downloads, engine)
        self._engine = engine
        self._runner = runner

    @Property(bool, notify=hasActiveChanged)
    def hasActive(self) -> bool:  # noqa: N802 (Qt property)
        return self.rowCount() > 0

    @Slot()
    def refresh(self) -> None:
        self._runner.run(self.reload())

    @Slot(str)
    def cancel(self, download_id: str) -> None:
        self._runner.run(self._cancel_then_reload(download_id))

    async def _cancel_then_reload(self, download_id: str) -> None:
        await self._cancel.execute(download_id)
        await self.reload()

    async def reload(self) -> None:
        downloads = await self._list.execute()
        rows = [await self._row(d) for d in downloads]
        had_active = self.rowCount() > 0
        self.replace_rows(rows)
        if had_active != (self.rowCount() > 0):
            self.hasActiveChanged.emit()

    async def _row(self, download: Download) -> Row:
        live_percent = await self._engine.progress_of(download.id)
        percent = max(download.progress_percent, live_percent)
        return {
            "id": download.id,
            "title": download.media.title,
            "platform": download.media.ref.platform.value,
            "progress": percent / 100.0,
            # A live capture has no known total: a "0%" bar would mislead.
            "progressKnown": download.media.kind is not MediaKind.STREAM,
            "statusLabel": _STATUS_LABELS.get(download.status, download.status.value),
        }
