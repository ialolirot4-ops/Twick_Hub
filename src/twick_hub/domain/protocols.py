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

from collections.abc import Collection, Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from twick_hub.domain.collections import Favorite, Playlist, ScheduledDownload
from twick_hub.domain.content import Clip, Stream, Video
from twick_hub.domain.downloads import Download, DownloadJob
from twick_hub.domain.enums import DownloadStatus
from twick_hub.domain.identity import Channel, PlatformAccount
from twick_hub.domain.migration import LegacyMigrationRun
from twick_hub.domain.monitoring import LiveStatusBatch
from twick_hub.domain.notifications import Notification
from twick_hub.domain.settings import Settings
from twick_hub.domain.updates import UpdateAttempt, UpdateInfo
from twick_hub.domain.value_objects import Media, PlatformRef, PlaybackSource

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
class BatchLiveStatusProvider(Protocol):
    """Live status for many channels in as few requests as the platform
    allows — the backend of every *polling* live monitor (FASE 10).
    Distinct from ``LiveStreamProvider``, which answers one channel per
    call: polling N favorites one call each is exactly the cost the
    batch endpoints (Kick ``/livestreams``, Twitch Helix ``/streams``)
    exist to avoid.

    Contract: raises ``domain.errors.RateLimitedError`` when the platform
    says to slow down, any other exception on failure — never a partial
    result presented as complete, since a channel missing from
    ``LiveStatusBatch.live`` means "offline".
    """

    async def get_live_streams(self, channel_refs: Sequence[PlatformRef]) -> LiveStatusBatch: ...


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
    async def list_all(self, *, limit: int | None = None, offset: int = 0) -> list[Favorite]: ...

    async def get_by_channel(self, channel_ref: PlatformRef) -> Favorite | None: ...

    async def save(self, favorite: Favorite) -> None: ...

    async def delete(self, favorite_id: str) -> None: ...


@runtime_checkable
class DownloadRepository(Protocol):
    async def list_all(self, *, limit: int | None = None, offset: int = 0) -> list[Download]: ...

    async def get(self, download_id: str) -> Download | None: ...

    async def save(self, download: Download) -> None: ...

    async def list_by_status(self, statuses: Collection[DownloadStatus]) -> list[Download]: ...


@runtime_checkable
class PlaylistRepository(Protocol):
    async def list_all(self, *, limit: int | None = None, offset: int = 0) -> list[Playlist]: ...

    async def get(self, playlist_id: str) -> Playlist | None: ...

    async def save(self, playlist: Playlist) -> None: ...

    async def delete(self, playlist_id: str) -> None: ...


@runtime_checkable
class ScheduledDownloadRepository(Protocol):
    async def list_all(
        self, *, limit: int | None = None, offset: int = 0
    ) -> list[ScheduledDownload]: ...

    async def save(self, scheduled: ScheduledDownload) -> None: ...

    async def delete(self, scheduled_id: str) -> None: ...


@runtime_checkable
class NotificationRepository(Protocol):
    async def list_unread(
        self, *, limit: int | None = None, offset: int = 0
    ) -> list[Notification]: ...

    async def save(self, notification: Notification) -> None: ...

    async def mark_read(self, notification_id: str) -> None: ...


@runtime_checkable
class SettingsRepository(Protocol):
    """One row, always present — ``get()`` never returns ``None`` (a
    fresh install has no saved row, so it returns ``Settings()``, the
    defaults, exactly like ``AppConfig`` runs with zero configuration).
    """

    async def get(self) -> Settings: ...

    async def save(self, settings: Settings) -> None: ...


@runtime_checkable
class UpdateSource(Protocol):
    """Where update manifests come from. ``check()`` either returns a
    fully origin-verified ``UpdateInfo`` (see domain/updates.py's module
    docstring — signature and host already checked by the time it
    returns) or raises ``UpdateOriginError``; there is no third outcome."""

    async def check(self) -> UpdateInfo | None: ...  # None: no manifest published yet


@runtime_checkable
class UpdateArtifactDownloader(Protocol):
    """What ``UpdateService`` needs from ``infrastructure.updates.UpdateDownloader``
    — split out as its own protocol (like every other application-layer
    dependency here) purely so tests can substitute a fake; there is only
    one real implementation."""

    async def download(self, info: UpdateInfo, destination: Path) -> Path: ...


@runtime_checkable
class UpdateInstaller(Protocol):
    """The packaging-dependent half of updating (docs/architecture-
    decisions.md's FASE 14 entry: real OS-specific installers are pending
    FASE 19's packaging decision). ``install()`` must itself back up
    whatever it needs to for ``rollback()`` to work — the caller doesn't
    manage that state."""

    async def install(self, artifact_path: str) -> None: ...

    async def rollback(self) -> None: ...


class UpdateAttemptRepository(Protocol):
    async def get(self, attempt_id: str) -> UpdateAttempt | None: ...

    async def list_all(
        self, *, limit: int | None = None, offset: int = 0
    ) -> list[UpdateAttempt]: ...

    async def save(self, attempt: UpdateAttempt) -> None: ...


@runtime_checkable
class LegacyMigrationRunRepository(Protocol):
    """FASE 15. ``find_by_source_hash`` is what makes a whole migration
    run idempotent (domain/migration.py's module docstring) — checked
    once, before any writes, instead of every repository call having to
    re-derive "did I already do this" from scratch."""

    async def get(self, run_id: str) -> LegacyMigrationRun | None: ...

    async def list_all(
        self, *, limit: int | None = None, offset: int = 0
    ) -> list[LegacyMigrationRun]: ...

    async def find_by_source_hash(self, source_sha256: str) -> LegacyMigrationRun | None: ...

    async def save(self, run: LegacyMigrationRun) -> None: ...


@runtime_checkable
class SecretTokenStore(Protocol):
    """Where a platform's durable secret (an OAuth/session token) is
    persisted — never in JSON/SQLite (Master Plan §52; AD-07).
    Deliberately narrower than ``AccountProvider``: FASE 15's migrator
    already has a token a legacy install obtained years ago, not a
    sign-in flow to run, so it needs "store/remove this token under this
    key," nothing more. ``infrastructure.twitch.token_store.TwitchTokenStore``
    satisfies this structurally.

    ``save``/``delete`` are synchronous here, matching
    ``TwitchTokenStore``'s own (pre-existing, FASE 12) interface — a
    deliberate mirror of that class's actual shape rather than a new
    inconsistency with this file's "every I/O method is async" rule.
    """

    def save(self, key: str, token: str) -> None: ...

    def delete(self, key: str) -> None: ...
