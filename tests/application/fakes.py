"""In-memory fakes for every domain protocol, used by application layer
tests. Proves the whole point of FASE 3's design: use cases are fully
testable against these, with no real Twitch/Kick/database/download
engine anywhere — those arrive in FASE 4+.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from twick_hub.domain.collections import Favorite, Playlist, ScheduledDownload
from twick_hub.domain.content import Clip, Stream, Video
from twick_hub.domain.downloads import Download, DownloadJob
from twick_hub.domain.identity import Channel, PlatformAccount, User
from twick_hub.domain.migration import LegacyMigrationRun
from twick_hub.domain.notifications import Notification
from twick_hub.domain.settings import Settings
from twick_hub.domain.updates import UpdateAttempt, UpdateInfo
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
class FakeLiveStreamProvider:
    streams: dict[str, Stream] = field(default_factory=dict)

    async def get_live_stream(self, channel_ref: PlatformRef) -> Stream | None:
        return self.streams.get(channel_ref.external_id)


@dataclass
class FakeAccountProvider:
    account: PlatformAccount | None = None

    async def connect(self) -> PlatformAccount:
        if self.account is None:
            raise LookupError("no account configured")
        return self.account

    async def disconnect(self) -> None:
        self.account = None

    async def current_account(self) -> PlatformAccount | None:
        return self.account


@dataclass
class FakeLiveMonitor:
    subscribed: set[str] = field(default_factory=set)

    async def subscribe(self, channel_ref: PlatformRef) -> None:
        self.subscribed.add(channel_ref.external_id)

    async def unsubscribe(self, channel_ref: PlatformRef) -> None:
        self.subscribed.discard(channel_ref.external_id)


@dataclass
class FakeVideoProvider:
    videos: dict[str, Video] = field(default_factory=dict)

    async def get_video(self, ref: PlatformRef) -> Video:
        video = self.videos.get(ref.external_id)
        if video is None:
            raise LookupError(f"no such video: {ref}")
        return video

    async def list_videos(self, channel_ref: PlatformRef) -> list[Video]:
        return [v for v in self.videos.values() if v.channel_ref == channel_ref]


@dataclass
class FakeClipProvider:
    clips: dict[str, Clip] = field(default_factory=dict)

    async def get_clip(self, ref: PlatformRef) -> Clip:
        clip = self.clips.get(ref.external_id)
        if clip is None:
            raise LookupError(f"no such clip: {ref}")
        return clip

    async def list_clips(self, channel_ref: PlatformRef) -> list[Clip]:
        return [c for c in self.clips.values() if c.channel_ref == channel_ref]


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

    async def list_all(self, *, limit: int | None = None, offset: int = 0) -> list[Favorite]:
        ordered = sorted(self._items.values(), key=lambda f: f.position)
        return ordered[offset : offset + limit if limit is not None else None]

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

    async def list_all(self, *, limit: int | None = None, offset: int = 0) -> list[Download]:
        return list(self._items.values())[offset : offset + limit if limit is not None else None]

    async def get(self, download_id: str) -> Download | None:
        return self._items.get(download_id)

    async def save(self, download: Download) -> None:
        self._items[download.id] = download

    async def list_by_status(self, statuses) -> list[Download]:
        return [d for d in self._items.values() if d.status in set(statuses)]


@dataclass
class InMemoryPlaylistRepository:
    _items: dict[str, Playlist] = field(default_factory=dict)

    async def list_all(self, *, limit: int | None = None, offset: int = 0) -> list[Playlist]:
        return list(self._items.values())[offset : offset + limit if limit is not None else None]

    async def get(self, playlist_id: str) -> Playlist | None:
        return self._items.get(playlist_id)

    async def save(self, playlist: Playlist) -> None:
        self._items[playlist.id] = playlist

    async def delete(self, playlist_id: str) -> None:
        self._items.pop(playlist_id, None)


@dataclass
class InMemoryScheduledDownloadRepository:
    _items: dict[str, ScheduledDownload] = field(default_factory=dict)

    async def list_all(
        self, *, limit: int | None = None, offset: int = 0
    ) -> list[ScheduledDownload]:
        end = offset + limit if limit is not None else None
        return list(self._items.values())[offset:end]

    async def save(self, scheduled: ScheduledDownload) -> None:
        self._items[scheduled.id] = scheduled

    async def delete(self, scheduled_id: str) -> None:
        self._items.pop(scheduled_id, None)


@dataclass
class InMemoryNotificationRepository:
    _items: dict[str, Notification] = field(default_factory=dict)

    async def list_unread(self, *, limit: int | None = None, offset: int = 0) -> list[Notification]:
        unread = [n for n in self._items.values() if not n.is_read]
        return unread[offset : offset + limit if limit is not None else None]

    async def save(self, notification: Notification) -> None:
        self._items[notification.id] = notification

    async def mark_read(self, notification_id: str) -> None:
        existing = self._items.get(notification_id)
        if existing is not None:
            self._items[notification_id] = replace(existing, is_read=True)


@dataclass
class InMemorySettingsRepository:
    _current: Settings | None = None

    async def get(self) -> Settings:
        return self._current if self._current is not None else Settings()

    async def save(self, settings: Settings) -> None:
        self._current = settings


@dataclass
class InMemoryUpdateAttemptRepository:
    _items: dict[str, UpdateAttempt] = field(default_factory=dict)

    async def get(self, attempt_id: str) -> UpdateAttempt | None:
        return self._items.get(attempt_id)

    async def list_all(self, *, limit: int | None = None, offset: int = 0) -> list[UpdateAttempt]:
        ordered = sorted(self._items.values(), key=lambda a: a.started_at, reverse=True)
        return ordered[offset : offset + limit if limit is not None else None]

    async def save(self, attempt: UpdateAttempt) -> None:
        self._items[attempt.id] = attempt


@dataclass
class FakeUpdateSource:
    info: UpdateInfo | None = None
    error: Exception | None = None

    async def check(self) -> UpdateInfo | None:
        if self.error is not None:
            raise self.error
        return self.info


@dataclass
class InMemoryLegacyMigrationRunRepository:
    _items: dict[str, LegacyMigrationRun] = field(default_factory=dict)

    async def get(self, run_id: str) -> LegacyMigrationRun | None:
        return self._items.get(run_id)

    async def list_all(
        self, *, limit: int | None = None, offset: int = 0
    ) -> list[LegacyMigrationRun]:
        ordered = sorted(self._items.values(), key=lambda r: r.started_at, reverse=True)
        return ordered[offset : offset + limit if limit is not None else None]

    async def find_by_source_hash(self, source_sha256: str) -> LegacyMigrationRun | None:
        matches = [r for r in self._items.values() if r.source_sha256 == source_sha256]
        if not matches:
            return None
        return max(matches, key=lambda r: r.started_at)

    async def save(self, run: LegacyMigrationRun) -> None:
        self._items[run.id] = run


@dataclass
class FakeSecretTokenStore:
    """Matches ``domain.protocols.SecretTokenStore`` — a stand-in for
    ``infrastructure.twitch.token_store.TwitchTokenStore`` that keeps
    tokens in a plain dict instead of a real OS credential store."""

    tokens: dict[str, str] = field(default_factory=dict)
    fail_on_save: Exception | None = None

    def save(self, key: str, token: str) -> None:
        if self.fail_on_save is not None:
            raise self.fail_on_save
        self.tokens[key] = token

    def load(self, key: str) -> str | None:
        return self.tokens.get(key)

    def delete(self, key: str) -> None:
        self.tokens.pop(key, None)
