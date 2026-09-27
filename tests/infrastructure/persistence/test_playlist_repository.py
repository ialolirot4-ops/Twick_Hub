from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from twick_hub.domain.collections import Playlist
from twick_hub.domain.enums import MediaKind, Platform
from twick_hub.domain.value_objects import Media, PlatformRef
from twick_hub.infrastructure.persistence.models import PlaylistItemRow
from twick_hub.infrastructure.persistence.playlist_repository import SqlPlaylistRepository


def _media(external_id: str) -> Media:
    ref = PlatformRef(platform=Platform.TWITCH, external_id=external_id)
    return Media(kind=MediaKind.VIDEO, ref=ref, title=external_id)


async def test_get_returns_none_when_absent(session_factory: sessionmaker):
    repo = SqlPlaylistRepository(session_factory)
    assert await repo.get("nope") is None


async def test_save_then_get_round_trips_an_empty_playlist(session_factory: sessionmaker):
    repo = SqlPlaylistRepository(session_factory)
    playlist = Playlist(name="Watch later")

    await repo.save(playlist)
    fetched = await repo.get(playlist.id)

    assert fetched == playlist


async def test_save_then_get_round_trips_items_in_position_order(session_factory: sessionmaker):
    repo = SqlPlaylistRepository(session_factory)
    playlist = Playlist(name="Highlights")
    playlist = playlist.with_item_added(_media("v1"))
    playlist = playlist.with_item_added(_media("v2"))
    playlist = playlist.with_item_added(_media("v3"))

    await repo.save(playlist)
    fetched = await repo.get(playlist.id)

    assert fetched == playlist
    assert fetched is not None
    assert [item.media.ref.external_id for item in fetched.items] == ["v1", "v2", "v3"]
    assert [item.position for item in fetched.items] == [0, 1, 2]


async def test_save_adding_an_item_to_an_already_saved_playlist_persists_the_new_item(
    session_factory: sessionmaker,
):
    repo = SqlPlaylistRepository(session_factory)
    playlist = Playlist(name="Growing")
    playlist = playlist.with_item_added(_media("v1"))
    await repo.save(playlist)

    grown = playlist.with_item_added(_media("v2"))
    await repo.save(grown)

    fetched = await repo.get(playlist.id)
    assert fetched is not None
    assert [item.media.ref.external_id for item in fetched.items] == ["v1", "v2"]


async def test_list_all_orders_most_recently_created_first(session_factory: sessionmaker):
    repo = SqlPlaylistRepository(session_factory)
    older = Playlist(name="Older", created_at=datetime(2026, 1, 1))
    newer = Playlist(name="Newer", created_at=datetime(2026, 1, 2))

    await repo.save(older)
    await repo.save(newer)

    result = await repo.list_all()
    assert [p.id for p in result] == [newer.id, older.id]


async def test_list_all_respects_limit_and_offset(session_factory: sessionmaker):
    repo = SqlPlaylistRepository(session_factory)
    base = datetime(2026, 1, 1)
    for i in range(5):
        await repo.save(Playlist(name=f"P{i}", created_at=base + timedelta(minutes=i)))

    page = await repo.list_all(limit=2, offset=1)

    assert [p.name for p in page] == ["P3", "P2"]


# --- FASE 12: delete, remove (orphan rows), reorder -------------------------


async def test_delete_removes_the_playlist(session_factory: sessionmaker):
    repo = SqlPlaylistRepository(session_factory)
    playlist = Playlist(name="Gone soon")
    await repo.save(playlist)

    await repo.delete(playlist.id)

    assert await repo.get(playlist.id) is None


async def test_delete_an_unknown_playlist_is_a_noop(session_factory: sessionmaker):
    repo = SqlPlaylistRepository(session_factory)
    await repo.delete("does-not-exist")  # must not raise


async def test_delete_removes_its_items_too_not_just_the_playlist_row(
    session_factory: sessionmaker,
):
    """The cascade is ORM-level ("all, delete-orphan"), so this checks the
    actual row count in playlist_items via a raw query — not just that
    ``get()`` returns None, which would also be true if the items were
    merely orphaned (parent gone, rows still sitting in the table)."""
    repo = SqlPlaylistRepository(session_factory)
    playlist = (
        Playlist(name="With items").with_item_added(_media("v1")).with_item_added(_media("v2"))
    )
    await repo.save(playlist)

    await repo.delete(playlist.id)

    with session_factory() as session:
        remaining = session.execute(
            text("SELECT COUNT(*) FROM playlist_items WHERE playlist_id = :pid"),
            {"pid": playlist.id},
        ).scalar_one()
    assert remaining == 0


async def test_saving_a_playlist_with_an_item_removed_deletes_that_items_row(
    session_factory: sessionmaker,
):
    repo = SqlPlaylistRepository(session_factory)
    playlist = (
        Playlist(name="Shrinking").with_item_added(_media("v1")).with_item_added(_media("v2"))
    )
    await repo.save(playlist)
    removed_item_id = playlist.items[0].id

    shrunk = playlist.with_item_removed(removed_item_id)
    await repo.save(shrunk)

    fetched = await repo.get(playlist.id)
    assert fetched is not None
    assert [item.media.ref.external_id for item in fetched.items] == ["v2"]
    assert [item.position for item in fetched.items] == [0]
    with session_factory() as session:
        row_still_there = session.get(PlaylistItemRow, removed_item_id)
    assert row_still_there is None  # actually deleted, not just detached


async def test_saving_a_reordered_playlist_persists_the_new_positions(
    session_factory: sessionmaker,
):
    repo = SqlPlaylistRepository(session_factory)
    playlist = (
        Playlist(name="Reordered").with_item_added(_media("v1")).with_item_added(_media("v2"))
    )
    await repo.save(playlist)
    first_id, second_id = (item.id for item in playlist.items)

    reordered = playlist.with_items_reordered([second_id, first_id])
    await repo.save(reordered)

    fetched = await repo.get(playlist.id)
    assert fetched is not None
    assert [item.id for item in fetched.items] == [second_id, first_id]
    assert [item.position for item in fetched.items] == [0, 1]


async def test_saving_a_renamed_playlist_persists_the_new_name(session_factory: sessionmaker):
    repo = SqlPlaylistRepository(session_factory)
    playlist = Playlist(name="Old name")
    await repo.save(playlist)

    await repo.save(playlist.renamed("New name"))

    fetched = await repo.get(playlist.id)
    assert fetched is not None and fetched.name == "New name"
