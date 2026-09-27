from dataclasses import replace
from pathlib import Path

import pytest

from tests.application.fakes import (
    FakeChannelDirectory,
    FakeDownloadEngine,
    FakePlaybackResolver,
    InMemoryDownloadRepository,
    InMemoryPlaylistRepository,
    make_channel,
)
from twick_hub.application.platform_registry import PlatformAdapters, PlatformRegistry
from twick_hub.application.playlists import (
    AddMediaToPlaylistUseCase,
    CreatePlaylistUseCase,
    DeletePlaylistUseCase,
    EnqueuePlaylistDownloadUseCase,
    ExportPlaylistUseCase,
    ImportPlaylistUseCase,
    PlaylistNotFoundError,
    RemoveMediaFromPlaylistUseCase,
    RenamePlaylistUseCase,
    ReorderPlaylistItemsUseCase,
)
from twick_hub.application.scheduling.destination import DestinationPlanner
from twick_hub.domain.collections import Playlist
from twick_hub.domain.downloads import Download
from twick_hub.domain.enums import MediaKind, Platform
from twick_hub.domain.value_objects import Media, PlatformRef

_MEDIA = Media(
    kind=MediaKind.CLIP, ref=PlatformRef(platform=Platform.KICK, external_id="c1"), title="A clip"
)


async def test_create_playlist_saves_it():
    playlists = InMemoryPlaylistRepository()
    playlist = await CreatePlaylistUseCase(playlists=playlists).execute("Highlights")

    assert playlist.name == "Highlights"
    assert await playlists.get(playlist.id) == playlist


async def test_add_media_to_playlist_persists_the_update():
    playlists = InMemoryPlaylistRepository()
    playlist = await CreatePlaylistUseCase(playlists=playlists).execute("Highlights")

    updated = await AddMediaToPlaylistUseCase(playlists=playlists).execute(playlist.id, _MEDIA)

    assert len(updated.items) == 1
    stored = await playlists.get(playlist.id)
    assert stored is not None
    assert stored.items[0].media == _MEDIA


async def test_add_media_to_unknown_playlist_raises():
    playlists = InMemoryPlaylistRepository()
    with pytest.raises(PlaylistNotFoundError):
        await AddMediaToPlaylistUseCase(playlists=playlists).execute("does-not-exist", _MEDIA)


# --- FASE 12: rename, delete, remove, reorder, export/import, download -----


async def test_rename_playlist_persists_the_new_name():
    playlists = InMemoryPlaylistRepository()
    playlist = await CreatePlaylistUseCase(playlists=playlists).execute("Highlights")

    renamed = await RenamePlaylistUseCase(playlists=playlists).execute(playlist.id, "Best of 2026")

    assert renamed.name == "Best of 2026"
    stored = await playlists.get(playlist.id)
    assert stored is not None and stored.name == "Best of 2026"


async def test_rename_unknown_playlist_raises():
    playlists = InMemoryPlaylistRepository()
    with pytest.raises(PlaylistNotFoundError):
        await RenamePlaylistUseCase(playlists=playlists).execute("nope", "X")


async def test_delete_playlist_removes_it():
    playlists = InMemoryPlaylistRepository()
    playlist = await CreatePlaylistUseCase(playlists=playlists).execute("Highlights")

    await DeletePlaylistUseCase(playlists=playlists).execute(playlist.id)

    assert await playlists.get(playlist.id) is None


async def test_delete_unknown_playlist_is_a_noop():
    playlists = InMemoryPlaylistRepository()
    await DeletePlaylistUseCase(playlists=playlists).execute("nope")  # must not raise


async def test_remove_media_from_playlist_persists_the_update():
    playlists = InMemoryPlaylistRepository()
    playlist = await CreatePlaylistUseCase(playlists=playlists).execute("Highlights")
    playlist = await AddMediaToPlaylistUseCase(playlists=playlists).execute(playlist.id, _MEDIA)
    item_id = playlist.items[0].id

    updated = await RemoveMediaFromPlaylistUseCase(playlists=playlists).execute(
        playlist.id, item_id
    )

    assert updated.items == ()
    stored = await playlists.get(playlist.id)
    assert stored is not None and stored.items == ()


async def test_remove_media_unknown_item_raises():
    playlists = InMemoryPlaylistRepository()
    playlist = await CreatePlaylistUseCase(playlists=playlists).execute("Highlights")
    with pytest.raises(ValueError, match="no item"):
        await RemoveMediaFromPlaylistUseCase(playlists=playlists).execute(playlist.id, "nope")


async def test_remove_media_from_unknown_playlist_raises_playlist_not_found():
    playlists = InMemoryPlaylistRepository()
    with pytest.raises(PlaylistNotFoundError):
        await RemoveMediaFromPlaylistUseCase(playlists=playlists).execute("nope", "item")


async def test_reorder_playlist_items_persists_the_new_order():
    playlists = InMemoryPlaylistRepository()
    playlist = await CreatePlaylistUseCase(playlists=playlists).execute("Highlights")
    playlist = await AddMediaToPlaylistUseCase(playlists=playlists).execute(playlist.id, _MEDIA)
    playlist = await AddMediaToPlaylistUseCase(playlists=playlists).execute(playlist.id, _MEDIA)
    first_id, second_id = (item.id for item in playlist.items)

    reordered = await ReorderPlaylistItemsUseCase(playlists=playlists).execute(
        playlist.id, [second_id, first_id]
    )

    assert [item.id for item in reordered.items] == [second_id, first_id]
    stored = await playlists.get(playlist.id)
    assert stored is not None
    assert [item.id for item in stored.items] == [second_id, first_id]


async def test_reorder_unknown_playlist_raises():
    playlists = InMemoryPlaylistRepository()
    with pytest.raises(PlaylistNotFoundError):
        await ReorderPlaylistItemsUseCase(playlists=playlists).execute("nope", [])


async def test_reorder_a_mismatched_order_raises_and_does_not_persist():
    playlists = InMemoryPlaylistRepository()
    playlist = await CreatePlaylistUseCase(playlists=playlists).execute("Highlights")
    playlist = await AddMediaToPlaylistUseCase(playlists=playlists).execute(playlist.id, _MEDIA)

    with pytest.raises(ValueError):
        await ReorderPlaylistItemsUseCase(playlists=playlists).execute(playlist.id, ["nope"])

    stored = await playlists.get(playlist.id)
    assert stored == playlist  # unchanged


async def test_export_then_import_round_trips_through_the_repository():
    playlists = InMemoryPlaylistRepository()
    playlist = await CreatePlaylistUseCase(playlists=playlists).execute("Highlights")
    playlist = await AddMediaToPlaylistUseCase(playlists=playlists).execute(playlist.id, _MEDIA)

    data = await ExportPlaylistUseCase(playlists=playlists).execute(playlist.id)
    imported = await ImportPlaylistUseCase(playlists=playlists).execute(data)

    assert imported.id != playlist.id
    assert imported.name == "Highlights"
    stored = await playlists.get(imported.id)
    assert stored == imported


async def test_export_unknown_playlist_raises():
    playlists = InMemoryPlaylistRepository()
    with pytest.raises(PlaylistNotFoundError):
        await ExportPlaylistUseCase(playlists=playlists).execute("nope")


async def test_import_with_a_name_override():
    playlists = InMemoryPlaylistRepository()
    playlist = await CreatePlaylistUseCase(playlists=playlists).execute("Original")
    data = await ExportPlaylistUseCase(playlists=playlists).execute(playlist.id)

    imported = await ImportPlaylistUseCase(playlists=playlists).execute(data, name="Copy")

    assert imported.name == "Copy"


async def test_import_malformed_data_raises_and_saves_nothing():
    playlists = InMemoryPlaylistRepository()
    with pytest.raises(ValueError):
        await ImportPlaylistUseCase(playlists=playlists).execute({"not": "valid"})
    assert await playlists.list_all() == []


# --- EnqueuePlaylistDownloadUseCase ------------------------------------------


def _download_env(qualities: list[str] | None = None):
    directory = FakeChannelDirectory()
    directory.add(make_channel("chan1", "streamer", Platform.KICK))
    resolver = FakePlaybackResolver(
        qualities=["1080p60", "720p60"] if qualities is None else qualities
    )
    registry = PlatformRegistry(
        {Platform.KICK: PlatformAdapters(channel_directory=directory, playback_resolver=resolver)}
    )
    downloads = InMemoryDownloadRepository()
    engine = FakeDownloadEngine()
    planner = DestinationPlanner(Path("/rec"), exists=lambda p: False)
    return registry, downloads, engine, planner


async def _playlist_with(playlists: InMemoryPlaylistRepository, *media: Media) -> Playlist:
    playlist = await CreatePlaylistUseCase(playlists=playlists).execute("Highlights")
    for item_media in media:
        playlist = await AddMediaToPlaylistUseCase(playlists=playlists).execute(
            playlist.id, item_media
        )
    return playlist


_MEDIA_WITH_CHANNEL = Media(
    kind=MediaKind.CLIP,
    ref=PlatformRef(platform=Platform.KICK, external_id="c1"),
    title="A clip",
    channel_ref=PlatformRef(platform=Platform.KICK, external_id="chan1"),
)
_MEDIA_WITH_CHANNEL_2 = Media(
    kind=MediaKind.VIDEO,
    ref=PlatformRef(platform=Platform.KICK, external_id="v1"),
    title="A VOD",
    channel_ref=PlatformRef(platform=Platform.KICK, external_id="chan1"),
)


async def test_download_playlist_enqueues_every_item_in_playlist_order():
    playlists = InMemoryPlaylistRepository()
    playlist = await _playlist_with(playlists, _MEDIA_WITH_CHANNEL, _MEDIA_WITH_CHANNEL_2)
    registry, downloads, engine, planner = _download_env()

    report = await EnqueuePlaylistDownloadUseCase(
        registry=registry, playlists=playlists, downloads=downloads, engine=engine, planner=planner
    ).execute(playlist.id)

    assert report.failed == ()
    assert len(report.enqueued) == 2
    assert [job.priority for job in engine.enqueued] == [0, 1]  # playlist position order
    assert all(d.quality_label == "1080p60" for d in report.enqueued)
    assert all(Path(d.destination_path).parent == Path("/rec/streamer") for d in report.enqueued)


async def test_download_playlist_gives_distinct_paths_for_same_titled_items():
    playlists = InMemoryPlaylistRepository()
    same_title = replace(_MEDIA_WITH_CHANNEL_2, title="Same Title")
    same_title_2 = replace(_MEDIA_WITH_CHANNEL, title="Same Title")
    playlist = await _playlist_with(playlists, same_title, same_title_2)
    registry, downloads, engine, planner = _download_env()

    report = await EnqueuePlaylistDownloadUseCase(
        registry=registry, playlists=playlists, downloads=downloads, engine=engine, planner=planner
    ).execute(playlist.id)

    paths = [d.destination_path for d in report.enqueued]
    assert len(set(paths)) == 2  # no collision


async def test_download_playlist_reports_a_missing_channel_but_still_downloads_with_the_id_folder():
    playlists = InMemoryPlaylistRepository()
    orphan = Media(
        kind=MediaKind.CLIP,
        ref=PlatformRef(platform=Platform.KICK, external_id="c9"),
        title="Orphan clip",
        channel_ref=PlatformRef(platform=Platform.KICK, external_id="unknown-channel"),
    )
    playlist = await _playlist_with(playlists, orphan)
    registry, downloads, engine, planner = _download_env()

    report = await EnqueuePlaylistDownloadUseCase(
        registry=registry, playlists=playlists, downloads=downloads, engine=engine, planner=planner
    ).execute(playlist.id)

    assert report.failed == ()
    assert Path(report.enqueued[0].destination_path).parent == Path("/rec/unknown-channel")


async def test_download_playlist_one_bad_item_does_not_abort_the_rest():
    playlists = InMemoryPlaylistRepository()
    playlist = await _playlist_with(playlists, _MEDIA_WITH_CHANNEL, _MEDIA_WITH_CHANNEL_2)
    registry, downloads, engine, planner = _download_env(
        qualities=[]
    )  # no qualities: every item fails

    report = await EnqueuePlaylistDownloadUseCase(
        registry=registry, playlists=playlists, downloads=downloads, engine=engine, planner=planner
    ).execute(playlist.id)

    assert report.enqueued == ()
    assert len(report.failed) == 2
    item_ids = {item.id for item in playlist.items}
    assert {item_id for item_id, _reason in report.failed} == item_ids


async def test_download_playlist_unknown_playlist_raises():
    registry, downloads, engine, planner = _download_env()
    with pytest.raises(PlaylistNotFoundError):
        await EnqueuePlaylistDownloadUseCase(
            registry=registry,
            playlists=InMemoryPlaylistRepository(),
            downloads=downloads,
            engine=engine,
            planner=planner,
        ).execute("nope")


async def test_download_playlist_respects_an_explicit_directory_override():
    playlists = InMemoryPlaylistRepository()
    playlist = await _playlist_with(playlists, _MEDIA_WITH_CHANNEL)
    registry, downloads, engine, planner = _download_env()

    report = await EnqueuePlaylistDownloadUseCase(
        registry=registry, playlists=playlists, downloads=downloads, engine=engine, planner=planner
    ).execute(playlist.id, directory="/elsewhere")

    assert Path(report.enqueued[0].destination_path).parent == Path("/elsewhere/streamer")


async def test_download_playlist_a_later_item_avoids_an_already_in_flight_download():
    playlists = InMemoryPlaylistRepository()
    playlist = await _playlist_with(playlists, _MEDIA_WITH_CHANNEL)
    registry, downloads, engine, planner = _download_env()
    # Something else already occupies the path this item would take.
    taken_path = str(Path("/rec/streamer/A clip (1080p60).mp4"))
    await downloads.save(
        Download(media=_MEDIA_WITH_CHANNEL_2, destination_path=taken_path, quality_label="1080p60")
    )
    # ... but the planner's default template includes date/time, so force a collision
    # by using a template that matches exactly what the use case will render.
    planner = DestinationPlanner(
        Path("/rec"), template="{channel}/{title} ({quality})", exists=lambda p: False
    )

    report = await EnqueuePlaylistDownloadUseCase(
        registry=registry, playlists=playlists, downloads=downloads, engine=engine, planner=planner
    ).execute(playlist.id)

    assert report.enqueued[0].destination_path != taken_path
    assert report.enqueued[0].destination_path == str(
        Path("/rec/streamer/A clip (1080p60) (2).mp4")
    )
