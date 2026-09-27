"""Restart recovery for downloads (Master Plan §48: "restart recovery").

A download is *durable* (its row survives a restart) but its worker is not:
after a crash or a normal shutdown mid-download, the row still says
DOWNLOADING and nothing is working on it. Left alone it would sit there
forever, and — worse for the scheduler — a scheduled download pointing at it
would wait for an ending that never comes.

What can be recovered depends on the kind of media, and that is a property
of the medium, not a design choice:

* **VOD / clip** — finished content at a stable URL, and ``SegmentManager``
  skips segments already on disk, so re-queueing continues where it left off.
* **Live stream** — the playback URL of a live capture only exists while the
  stream does, and the moment of the interruption is gone for good. It is
  marked FAILED (not silently dropped: history should show the truth). If the
  channel is still live and something wants it recorded, a fresh recording
  starts through the normal path — the live monitor reports an ``initial``
  go-live on startup for exactly that reason.

``PAUSED`` downloads are left alone: pausing is the user's decision, and
``DownloadService.resume()`` now re-queues one that no worker owns.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from twick_hub.domain.downloads import DownloadJob
from twick_hub.domain.enums import DownloadStatus, MediaKind
from twick_hub.domain.protocols import DownloadEngine, DownloadRepository

INTERRUPTED_MESSAGE = "interrupted by application shutdown"

_INTERRUPTED = (
    DownloadStatus.QUEUED,
    DownloadStatus.PREPARING,
    DownloadStatus.DOWNLOADING,
    DownloadStatus.PROCESSING,
)


@dataclass(frozen=True, slots=True)
class RecoveryReport:
    failed_streams: tuple[str, ...] = ()
    requeued: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RecoverInterruptedDownloadsUseCase:
    downloads: DownloadRepository
    engine: DownloadEngine

    async def execute(self) -> RecoveryReport:
        failed: list[str] = []
        requeued: list[str] = []
        for download in await self.downloads.list_by_status(_INTERRUPTED):
            if download.media.kind is MediaKind.STREAM:
                await self.downloads.save(
                    replace(
                        download, status=DownloadStatus.FAILED, error_message=INTERRUPTED_MESSAGE
                    )
                )
                failed.append(download.id)
            else:
                await self.downloads.save(replace(download, status=DownloadStatus.QUEUED))
                await self.engine.enqueue(DownloadJob(download_id=download.id))
                requeued.append(download.id)
        return RecoveryReport(failed_streams=tuple(failed), requeued=tuple(requeued))
