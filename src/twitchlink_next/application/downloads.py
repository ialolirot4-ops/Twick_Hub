"""Download use cases."""

from __future__ import annotations

from dataclasses import dataclass, replace

from twitchlink_next.domain.downloads import Download, DownloadJob
from twitchlink_next.domain.enums import DownloadStatus
from twitchlink_next.domain.protocols import DownloadEngine, DownloadRepository, PlaybackResolver
from twitchlink_next.domain.value_objects import Media


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
