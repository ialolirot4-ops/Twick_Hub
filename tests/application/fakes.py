"""In-memory fakes for every domain protocol, used by application layer
tests. Proves the whole point of FASE 3's design: use cases are fully
testable against these, with no real Twitch/Kick/database/download
engine anywhere — those arrive in FASE 4+.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from twick_hub.domain.collections import Favorite, Playlist, ScheduledDownload
from twick_hub.domain.downloads import Download, DownloadJob
from twick_hub.domain.identity import Channel, User
from twick_hub.domain.notifications import Notification
from twick_hub.domain.value_objects import Media, PlatformRef, PlaybackSource


@dataclass
class FakeChannelDirectory:
    channels: dict[str, Channel] = field(default_factory=dict)

    def add(self, channel: Channel) -> None:
        self.channels[channel.ref.external_id] = channel

    async def find_channel(self, query: str) -> Channel | None:
        return self.channels.get(query)

    async def get_channel(self, ref: PlatformRef) -> Channel:
        channel = self.channels.get(ref.external_id)
        if channel is None:
            raise LookupError(f"no such channel: {ref}")
        return channel


def make_channel(external_id: str, username: str, platform) -> Channel:
    ref = PlatformRef(platform=platform, external_id=external_id)
    return Channel(ref=ref, user=User(ref=ref, username=username, display_name=username))


@dataclass
class FakePlaybackResolver:
    qualities: list[str] = field(default_factory=lambda: ["source", "720p", "480p"])

    async def resolve(self, media: Media, quality: str) -> PlaybackSource:
        url = f"https://example.invalid/{media.ref.external_id}/{quality}.m3u8"
        return PlaybackSource(url=url, quality_label=quality)

    async def available_qualities(self, media: Media) -> list[str]:
        return list(self.qualities)


@dataclass
class FakeDownloadEngine:
    enqueued: list[DownloadJob] = field(default_factory=list)
    cancelled: list[str] = field(default_factory=list)

    async def enqueue(self, job: DownloadJob) -> None:
        self.enqueued.append(job)

    async def cancel(self, job_id: str) -> None:
        self.cancelled.append(job_id)

    async def progress_of(self, job_id: str) -> float:
        return 0.0


@dataclass
class InMemoryFavoriteRepository:
    _items: dict[str, Favorite] = field(default_factory=dict)

    async def list_all(self) -> list[Favorite]:
        return list(self._items.values())

    async def get_by_channel(self, channel_ref: PlatformRef) -> Favorite | None:
        for favorite in self._items.values():
            if favorite.channel_ref == channel_ref:
                return favorite
        return None

    async def save(self, favorite: Favorite) -> None:
        self._items[favorite.id] = favorite

    async def delete(self, favorite_id: str) -> None:
        self._items.pop(favorite_id, None)


@dataclass
class InMemoryDownloadRepository:
    _items: dict[str, Download] = field(default_factory=dict)

    async def list_all(self) -> list[Download]:
        return list(self._items.values())

    async def get(self, download_id: str) -> Download | None:
        return self._items.get(download_id)

    async def save(self, download: Download) -> None:
        self._items[download.id] = download


@dataclass
class InMemoryPlaylistRepository:
    _items: dict[str, Playlist] = field(default_factory=dict)

    async def list_all(self) -> list[Playlist]:
        return list(self._items.values())

    async def get(self, playlist_id: str) -> Playlist | None:
        return self._items.get(playlist_id)

    async def save(self, playlist: Playlist) -> None:
        self._items[playlist.id] = playlist


@dataclass
class InMemoryScheduledDownloadRepository:
    _items: dict[str, ScheduledDownload] = field(default_factory=dict)

    async def list_all(self) -> list[ScheduledDownload]:
        return list(self._items.values())

    async def save(self, scheduled: ScheduledDownload) -> None:
        self._items[scheduled.id] = scheduled

    async def delete(self, scheduled_id: str) -> None:
        self._items.pop(scheduled_id, None)


@dataclass
class InMemoryNotificationRepository:
    _items: dict[str, Notification] = field(default_factory=dict)

    async def list_unread(self) -> list[Notification]:
        return [n for n in self._items.values() if not n.is_read]

    async def save(self, notification: Notification) -> None:
        self._items[notification.id] = notification

    async def mark_read(self, notification_id: str) -> None:
        existing = self._items.get(notification_id)
        if existing is not None:
            self._items[notification_id] = replace(existing, is_read=True)
