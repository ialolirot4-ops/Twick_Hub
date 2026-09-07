"""Domain protocols — the interfaces Application depends on and
Infrastructure implements starting FASE 4+. Nothing in this file talks to
a real platform, database, or download engine; that's the whole point
(Master Plan's permanent rules: "mantener Twitch/Kick detrás de
interfaces comunes", "mantener particularidades de cada plataforma
aisladas en adapters").

Split into several narrow protocols instead of one fat "PlatformClient"
on purpose: docs/risk-register.md (RISK-TWITCH-03) already named
``VideoProvider``/``ClipProvider`` as the isolation boundary for Twitch's
unofficial GraphQL API, and docs/kick-audit.md found Kick's official API
doesn't cover VOD/Clips at all. A platform adapter implements whichever
of these protocols it can actually back — Kick's adapter (FASE 5) is
free to not implement VideoProvider/ClipProvider until/unless Kick
officializes them, rather than being forced to fake methods it can't
support.

Every I/O-bound method is ``async`` — nothing here may block the UI
thread (a permanent rule from the Master Plan), and every real
implementation (Twitch's GQL/Helix calls, Kick's REST calls, SQLAlchemy
queries) is I/O.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from twitchlink_next.domain.collections import Favorite, Playlist, ScheduledDownload
from twitchlink_next.domain.content import Clip, Stream, Video
from twitchlink_next.domain.downloads import Download, DownloadJob
from twitchlink_next.domain.identity import Channel, PlatformAccount
from twitchlink_next.domain.notifications import Notification
from twitchlink_next.domain.value_objects import Media, PlatformRef, PlaybackSource

# --- platform capabilities -------------------------------------------------


@runtime_checkable
class AccountProvider(Protocol):
    """Connects/disconnects the app's own identity on a platform (Master
    Plan §38, FASE 4a: "account"). Distinct from ``ChannelDirectory``,
    which looks up *any* channel — this is specifically about *this
    installation's* signed-in state.
    """

    async def connect(self) -> PlatformAccount: ...

    async def disconnect(self) -> None: ...

    async def current_account(self) -> PlatformAccount | None: ...


@runtime_checkable
class ChannelDirectory(Protocol):
    """Look up channels by URL/handle or by platform id. Every platform
    adapter implements this — it's the minimum needed for Search,
    Favorites, and Account to function at all.
    """

    async def find_channel(self, query: str) -> Channel | None: ...

    async def get_channel(self, ref: PlatformRef) -> Channel: ...


@runtime_checkable
class LiveStreamProvider(Protocol):
    async def get_live_stream(self, channel_ref: PlatformRef) -> Stream | None: ...


@runtime_checkable
class VideoProvider(Protocol):
    """Not every platform adapter implements this — see this module's
    docstring. Absence of an implementation means "not available on this
    platform," not an error to work around.
    """

    async def get_video(self, ref: PlatformRef) -> Video: ...

    async def list_videos(self, channel_ref: PlatformRef) -> list[Video]: ...


@runtime_checkable
class ClipProvider(Protocol):
    async def get_clip(self, ref: PlatformRef) -> Clip: ...

    async def list_clips(self, channel_ref: PlatformRef) -> list[Clip]: ...


@runtime_checkable
class PlaybackResolver(Protocol):
    """Resolves a Media reference to an actual, downloadable source at a
    given quality. Twitch's implementation (FASE 4c) goes through the
    GQL playback-access-token flow; a platform's absence of this
    protocol means it has no known way to fetch playable media at all.
    """

    async def resolve(self, media: Media, quality: str) -> PlaybackSource: ...

    async def available_qualities(self, media: Media) -> list[str]: ...


@runtime_checkable
class LiveMonitor(Protocol):
    """Unifies Twitch's EventSub and Kick's adaptive polling
    (docs/architecture-decisions.md AD-04/AD-06) behind one interface —
    callers subscribe/unsubscribe without knowing which mechanism is
    behind either platform.
    """

    async def subscribe(self, channel_ref: PlatformRef) -> None: ...

    async def unsubscribe(self, channel_ref: PlatformRef) -> None: ...


@runtime_checkable
class DownloadEngine(Protocol):
    """The FASE 7 download engine's boundary, as seen by Application."""

    async def enqueue(self, job: DownloadJob) -> None: ...

    async def cancel(self, job_id: str) -> None: ...

    async def progress_of(self, job_id: str) -> float: ...


# --- persistence -------------------------------------------------


@runtime_checkable
class ChannelRepository(Protocol):
    async def get(self, ref: PlatformRef) -> Channel | None: ...

    async def save(self, channel: Channel) -> None: ...


@runtime_checkable
class FavoriteRepository(Protocol):
    async def list_all(self) -> list[Favorite]: ...

    async def get_by_channel(self, channel_ref: PlatformRef) -> Favorite | None: ...

    async def save(self, favorite: Favorite) -> None: ...

    async def delete(self, favorite_id: str) -> None: ...


@runtime_checkable
class DownloadRepository(Protocol):
    async def list_all(self) -> list[Download]: ...

    async def get(self, download_id: str) -> Download | None: ...

    async def save(self, download: Download) -> None: ...


@runtime_checkable
class PlaylistRepository(Protocol):
    async def list_all(self) -> list[Playlist]: ...

    async def get(self, playlist_id: str) -> Playlist | None: ...

    async def save(self, playlist: Playlist) -> None: ...


@runtime_checkable
class ScheduledDownloadRepository(Protocol):
    async def list_all(self) -> list[ScheduledDownload]: ...

    async def save(self, scheduled: ScheduledDownload) -> None: ...

    async def delete(self, scheduled_id: str) -> None: ...


@runtime_checkable
class NotificationRepository(Protocol):
    async def list_unread(self) -> list[Notification]: ...

    async def save(self, notification: Notification) -> None: ...

    async def mark_read(self, notification_id: str) -> None: ...
