"""Scheduled download use cases."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from twick_hub.domain.collections import ScheduledDownload
from twick_hub.domain.enums import ScheduleTrigger
from twick_hub.domain.protocols import ChannelDirectory, ScheduledDownloadRepository
from twick_hub.domain.value_objects import PlatformRef


@dataclass(frozen=True, slots=True)
class CreateScheduledDownloadUseCase:
    channel_directory: ChannelDirectory
    scheduled_downloads: ScheduledDownloadRepository
    clock: Callable[[], datetime] = datetime.now

    async def execute(
        self,
        channel_ref: PlatformRef,
        trigger: ScheduleTrigger,
        quality_preference: str = "best",
        *,
        run_at: datetime | None = None,
        weekdays: tuple[int, ...] = (),
        window_seconds: int = 4 * 3600,
        priority: int = 0,
        max_attempts: int = 3,
        download_directory: str | None = None,
        preferred_format: str | None = None,
    ) -> ScheduledDownload:
        # Confirms the channel actually exists before scheduling anything
        # against it — the same defensive lookup AddFavoriteUseCase does.
        channel = await self.channel_directory.get_channel(channel_ref)

        scheduled = ScheduledDownload(
            channel_ref=channel.ref,
            trigger=trigger,
            quality_preference=quality_preference,
            run_at=run_at,
            weekdays=weekdays,
            window_seconds=window_seconds,
            priority=priority,
            max_attempts=max_attempts,
            download_directory=download_directory,
            preferred_format=preferred_format,
        ).with_first_due(self.clock())
        await self.scheduled_downloads.save(scheduled)
        return scheduled


@dataclass(frozen=True, slots=True)
class CancelScheduledDownloadUseCase:
    scheduled_downloads: ScheduledDownloadRepository

    async def execute(self, scheduled_id: str) -> None:
        await self.scheduled_downloads.delete(scheduled_id)
