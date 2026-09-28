"""Download use cases."""

from __future__ import annotations

from dataclasses import dataclass, replace

from twick_hub.domain.downloads import Download, DownloadJob
from twick_hub.domain.enums import DownloadStatus
from twick_hub.domain.protocols import DownloadEngine, DownloadRepository, PlaybackResolver
from twick_hub.domain.value_objects import Media


class QualityNotAvailableError(Exception):
    """Raised when the requested quality isn't in
    ``PlaybackResolver.available_qualities`` for this Media."""


@dataclass(frozen=True, slots=True)
class EnqueueDownloadUseCase:
    playback: PlaybackResolver
    downloads: DownloadRepository
    engine: DownloadEngine

    async def execute(self, media: Media, destination_path: str, quality: str) -> Download:
        available = await self.playback.available_qualities(media)
        if quality not in available:
            raise QualityNotAvailableError(
                f"'{quality}' is not available for this media (have: {', '.join(available)})"
            )

        download = Download(media=media, destination_path=destination_path, quality_label=quality)
        await self.downloads.save(download)

        job = DownloadJob(download_id=download.id)
        await self.engine.enqueue(job)
        return download


@dataclass(frozen=True, slots=True)
class CancelDownloadUseCase:
    downloads: DownloadRepository
    engine: DownloadEngine

    async def execute(self, download_id: str) -> None:
        download = await self.downloads.get(download_id)
        if download is None:
            return
        await self.engine.cancel(download_id)
        await self.downloads.save(replace(download, status=DownloadStatus.CANCELLED))


# Statuses a download can still leave (FASE 21b). ``PAUSED`` counts as
# active: it is resumable, so the Downloads page keeps showing it.
ACTIVE_DOWNLOAD_STATUSES: frozenset[DownloadStatus] = frozenset(
    {
        DownloadStatus.QUEUED,
        DownloadStatus.PREPARING,
        DownloadStatus.DOWNLOADING,
        DownloadStatus.PROCESSING,
        DownloadStatus.PAUSED,
    }
)
FINISHED_DOWNLOAD_STATUSES: frozenset[DownloadStatus] = frozenset(
    {DownloadStatus.COMPLETED, DownloadStatus.FAILED, DownloadStatus.CANCELLED}
)


@dataclass(frozen=True, slots=True)
class ListActiveDownloadsUseCase:
    """Downloads still in flight, oldest first (queue order)."""

    downloads: DownloadRepository

    async def execute(self) -> list[Download]:
        active = await self.downloads.list_by_status(ACTIVE_DOWNLOAD_STATUSES)
        return sorted(active, key=lambda d: d.created_at)


@dataclass(frozen=True, slots=True)
class ListDownloadHistoryUseCase:
    """Finished downloads (completed, failed or cancelled), newest first."""

    downloads: DownloadRepository

    async def execute(self) -> list[Download]:
        finished = await self.downloads.list_by_status(FINISHED_DOWNLOAD_STATUSES)
        return sorted(finished, key=lambda d: d.completed_at or d.created_at, reverse=True)
