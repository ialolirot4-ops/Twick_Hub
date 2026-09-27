"""Playlist use cases (Master Plan §49, FASE 12: create; rename; delete;
reorder; add; remove; download; import/export si procede).

``CreatePlaylistUseCase``/``AddMediaToPlaylistUseCase`` are FASE 3's
originals, unchanged. Everything else is FASE 12.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from twick_hub.application.platform_registry import PlatformRegistry
from twick_hub.application.scheduling.destination import DestinationPlanner
from twick_hub.application.scheduling.quality import NoQualitiesError, select_quality
from twick_hub.domain.collections import Playlist
from twick_hub.domain.downloads import Download, DownloadJob
from twick_hub.domain.enums import DownloadStatus
from twick_hub.domain.protocols import DownloadEngine, DownloadRepository, PlaylistRepository
from twick_hub.domain.value_objects import Media

_IN_FLIGHT = (
    DownloadStatus.QUEUED,
    DownloadStatus.PREPARING,
    DownloadStatus.DOWNLOADING,
    DownloadStatus.PROCESSING,
    DownloadStatus.PAUSED,
)


class PlaylistNotFoundError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class CreatePlaylistUseCase:
    playlists: PlaylistRepository

    async def execute(self, name: str) -> Playlist:
        playlist = Playlist(name=name)
        await self.playlists.save(playlist)
        return playlist


@dataclass(frozen=True, slots=True)
class AddMediaToPlaylistUseCase:
    playlists: PlaylistRepository

    async def execute(self, playlist_id: str, media: Media) -> Playlist:
        playlist = await self._get_or_raise(playlist_id)
        updated = playlist.with_item_added(media)
        await self.playlists.save(updated)
        return updated

    async def _get_or_raise(self, playlist_id: str) -> Playlist:
        playlist = await self.playlists.get(playlist_id)
        if playlist is None:
            raise PlaylistNotFoundError(playlist_id)
        return playlist


@dataclass(frozen=True, slots=True)
class RenamePlaylistUseCase:
    playlists: PlaylistRepository

    async def execute(self, playlist_id: str, name: str) -> Playlist:
        playlist = await self._get_or_raise(playlist_id)
        renamed = playlist.renamed(name)
        await self.playlists.save(renamed)
        return renamed

    async def _get_or_raise(self, playlist_id: str) -> Playlist:
        playlist = await self.playlists.get(playlist_id)
        if playlist is None:
            raise PlaylistNotFoundError(playlist_id)
        return playlist


@dataclass(frozen=True, slots=True)
class DeletePlaylistUseCase:
    playlists: PlaylistRepository

    async def execute(self, playlist_id: str) -> None:
        """Idempotent, like ``FavoriteRepository.delete`` and
        ``ScheduledDownloadRepository.delete`` — deleting an already-gone
        playlist is a no-op, not an error."""
        await self.playlists.delete(playlist_id)


@dataclass(frozen=True, slots=True)
class RemoveMediaFromPlaylistUseCase:
    playlists: PlaylistRepository

    async def execute(self, playlist_id: str, item_id: str) -> Playlist:
        playlist = await self._get_or_raise(playlist_id)
        updated = playlist.with_item_removed(item_id)  # raises ValueError if item_id isn't there
        await self.playlists.save(updated)
        return updated

    async def _get_or_raise(self, playlist_id: str) -> Playlist:
        playlist = await self.playlists.get(playlist_id)
        if playlist is None:
            raise PlaylistNotFoundError(playlist_id)
        return playlist


@dataclass(frozen=True, slots=True)
class ReorderPlaylistItemsUseCase:
    playlists: PlaylistRepository

    async def execute(self, playlist_id: str, item_ids: Sequence[str]) -> Playlist:
        playlist = await self._get_or_raise(playlist_id)
        reordered = playlist.with_items_reordered(item_ids)  # raises ValueError on a mismatch
        await self.playlists.save(reordered)
        return reordered

    async def _get_or_raise(self, playlist_id: str) -> Playlist:
        playlist = await self.playlists.get(playlist_id)
        if playlist is None:
            raise PlaylistNotFoundError(playlist_id)
        return playlist


@dataclass(frozen=True, slots=True)
class ExportPlaylistUseCase:
    playlists: PlaylistRepository

    async def execute(self, playlist_id: str) -> dict:
        playlist = await self.playlists.get(playlist_id)
        if playlist is None:
            raise PlaylistNotFoundError(playlist_id)
        return playlist.to_export_dict()


@dataclass(frozen=True, slots=True)
class ImportPlaylistUseCase:
    playlists: PlaylistRepository

    async def execute(self, data: dict, *, name: str | None = None) -> Playlist:
        playlist = Playlist.from_export_dict(data, name=name)  # raises ValueError on malformed data
        await self.playlists.save(playlist)
        return playlist


@dataclass(frozen=True, slots=True)
class PlaylistDownloadReport:
    """Partial failure is expected, not exceptional, for a batch spanning
    several platforms and possibly-stale media (Master Plan permanent
    rule: no asumir — one bad item, e.g. a deleted VOD, must not abort
    everything after it). Same shape as FASE 10's ``SyncReport`` and
    FASE 11's ``RecoveryReport``."""

    enqueued: tuple[Download, ...] = ()
    failed: tuple[tuple[str, str], ...] = ()  # (item_id, reason)


@dataclass(frozen=True, slots=True)
class EnqueuePlaylistDownloadUseCase:
    """Downloads every item in a playlist through the FASE 7 download
    engine, dispatching each item to its own platform's adapters via
    ``PlatformRegistry`` — unlike ``EnqueueDownloadUseCase`` (FASE 3),
    which takes a single ``PlaybackResolver`` and so can only ever serve
    one platform at a time (docs/risk-register.md RISK-ARCH-02). A
    playlist routinely mixes Twitch and Kick items, so that shortcut
    isn't available here; this does the per-item platform dispatch
    properly instead of reproducing the same gap.

    Reuses FASE 11's quality fallback (``select_quality``) and
    destination planning (``DestinationPlanner``, with the growing batch
    of ``Download`` rows this call itself creates protecting later items
    in the same call from colliding on the same filename) rather than
    inventing a second copy of either.
    """

    registry: PlatformRegistry
    playlists: PlaylistRepository
    downloads: DownloadRepository
    engine: DownloadEngine
    planner: DestinationPlanner
    clock: Callable[[], datetime] = datetime.now

    async def execute(
        self,
        playlist_id: str,
        *,
        quality_preference: str = "best",
        directory: str | None = None,
    ) -> PlaylistDownloadReport:
        playlist = await self.playlists.get(playlist_id)
        if playlist is None:
            raise PlaylistNotFoundError(playlist_id)

        enqueued: list[Download] = []
        failed: list[tuple[str, str]] = []
        for item in playlist.items:
            try:
                download = await self._enqueue_one(
                    item.media, quality_preference, directory, item.position
                )
            except Exception as exc:  # noqa: BLE001 - reported per item, never abandons the rest
                failed.append((item.id, str(exc)))
                continue
            enqueued.append(download)
        return PlaylistDownloadReport(enqueued=tuple(enqueued), failed=tuple(failed))

    async def _enqueue_one(
        self, media: Media, quality_preference: str, directory: str | None, priority: int
    ) -> Download:
        qualities = await self.registry.available_qualities(media)
        try:
            choice = select_quality(quality_preference, qualities)
        except NoQualitiesError as exc:
            raise NoQualitiesError(f"{media.title}: {exc}") from exc

        now = self.clock()
        destination = self.planner.plan(
            {
                "channel": await self._channel_name(media),
                "title": media.title or media.kind.value,
                "quality": choice.label,
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%H-%M-%S"),
            },
            directory=directory,
            reserved=[d.destination_path for d in await self.downloads.list_by_status(_IN_FLIGHT)],
        )

        download = Download(media=media, destination_path=destination, quality_label=choice.label)
        await self.downloads.save(download)
        try:
            await self.engine.enqueue(DownloadJob(download_id=download.id, priority=priority))
        except Exception:
            from dataclasses import replace as _replace

            await self.downloads.save(_replace(download, status=DownloadStatus.FAILED))
            raise
        return download

    async def _channel_name(self, media: Media) -> str:
        if media.channel_ref is None:
            return "unknown"
        try:
            return (await self.registry.get_channel(media.channel_ref)).user.username
        except Exception:  # noqa: BLE001 - a missing display name must not block a download
            return media.channel_ref.external_id
