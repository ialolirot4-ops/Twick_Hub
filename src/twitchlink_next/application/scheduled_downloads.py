"""Scheduled download use cases."""

from __future__ import annotations

from dataclasses import dataclass

from twitchlink_next.domain.collections import ScheduledDownload
from twitchlink_next.domain.enums import ScheduleTrigger
from twitchlink_next.domain.protocols import ChannelDirectory, ScheduledDownloadRepository
from twitchlink_next.domain.value_objects import PlatformRef


@dataclass(frozen=True, slots=True)
class CreateScheduledDownloadUseCase:
    channel_directory: ChannelDirectory
    scheduled_downloads: ScheduledDownloadRepository

    async def execute(
        self, channel_ref: PlatformRef, trigger: ScheduleTrigger, quality_preference: str = "best"
    ) -> ScheduledDownload:
        # Confirms the channel actually exists before scheduling anything
        # against it — the same defensive lookup AddFavoriteUseCase does.
        channel = await self.channel_directory.get_channel(channel_ref)

        scheduled = ScheduledDownload(
            channel_ref=channel.ref, trigger=trigger, quality_preference=quality_preference
        )
        await self.scheduled_downloads.save(scheduled)
        return scheduled


@dataclass(frozen=True, slots=True)
class CancelScheduledDownloadUseCase:
    scheduled_downloads: ScheduledDownloadRepository

    async def execute(self, scheduled_id: str) -> None:
        await self.scheduled_downloads.delete(scheduled_id)
