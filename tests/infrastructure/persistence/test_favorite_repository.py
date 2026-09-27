from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from sqlalchemy.orm import sessionmaker

from twick_hub.domain.collections import Favorite
from twick_hub.domain.enums import Platform
from twick_hub.domain.value_objects import PlatformRef
from twick_hub.infrastructure.persistence.favorite_repository import SqlFavoriteRepository


def _favorite(external_id: str, position: int = 0) -> Favorite:
    ref = PlatformRef(platform=Platform.TWITCH, external_id=external_id)
    return Favorite(channel_ref=ref, added_at=datetime(2026, 1, 1), position=position)


async def test_get_by_channel_returns_none_when_absent(session_factory: sessionmaker):
    repo = SqlFavoriteRepository(session_factory)
    ref = PlatformRef(platform=Platform.TWITCH, external_id="nope")
    assert await repo.get_by_channel(ref) is None


async def test_save_then_get_by_channel_round_trips(session_factory: sessionmaker):
    repo = SqlFavoriteRepository(session_factory)
    favorite = _favorite("c1")

    await repo.save(favorite)
    fetched = await repo.get_by_channel(favorite.channel_ref)

    assert fetched == favorite


async def test_save_round_trips_quality_format_and_directory(session_factory: sessionmaker):
    repo = SqlFavoriteRepository(session_factory)
    favorite = replace(
        _favorite("c1"),
        preferred_quality="720p",
        preferred_format="mkv",
        download_directory="/home/user/Videos/NL",
    )

    await repo.save(favorite)
    fetched = await repo.get_by_channel(favorite.channel_ref)

    assert fetched == favorite


async def test_save_round_trips_with_no_quality_format_or_directory_set(
    session_factory: sessionmaker,
):
    repo = SqlFavoriteRepository(session_factory)
    favorite = _favorite("c1")

    await repo.save(favorite)
    fetched = await repo.get_by_channel(favorite.channel_ref)

    assert fetched is not None
    assert fetched.preferred_quality is None
    assert fetched.preferred_format is None
    assert fetched.download_directory is None


async def test_save_upserts_by_id_not_by_channel(session_factory: sessionmaker):
    repo = SqlFavoriteRepository(session_factory)
    favorite = _favorite("c1")
    await repo.save(favorite)

    updated = replace(favorite, notify_on_live=False, auto_download=True)
    await repo.save(updated)

    assert await repo.get_by_channel(favorite.channel_ref) == updated
    assert len(await repo.list_all()) == 1


async def test_delete_removes_the_favorite(session_factory: sessionmaker):
    repo = SqlFavoriteRepository(session_factory)
    favorite = _favorite("c1")
    await repo.save(favorite)

    await repo.delete(favorite.id)

    assert await repo.get_by_channel(favorite.channel_ref) is None
    assert await repo.list_all() == []


async def test_delete_of_unknown_id_does_not_raise(session_factory: sessionmaker):
    repo = SqlFavoriteRepository(session_factory)
    await repo.delete("does-not-exist")


async def test_list_all_orders_by_position(session_factory: sessionmaker):
    repo = SqlFavoriteRepository(session_factory)
    first = _favorite("c1", position=0)
    second = _favorite("c2", position=1)

    # save in reverse order — must come back ordered by `position`, not insertion order
    await repo.save(second)
    await repo.save(first)

    result = await repo.list_all()
    assert [f.id for f in result] == [first.id, second.id]


async def test_reordering_persists_the_new_position(session_factory: sessionmaker):
    repo = SqlFavoriteRepository(session_factory)
    first = _favorite("c1", position=0)
    second = _favorite("c2", position=1)
    await repo.save(first)
    await repo.save(second)

    await repo.save(replace(first, position=1))
    await repo.save(replace(second, position=0))

    result = await repo.list_all()
    assert [f.id for f in result] == [second.id, first.id]


async def test_list_all_respects_limit_and_offset(session_factory: sessionmaker):
    repo = SqlFavoriteRepository(session_factory)
    favorites = [_favorite(f"c{i}", position=i) for i in range(5)]
    for favorite in favorites:
        await repo.save(favorite)

    page = await repo.list_all(limit=2, offset=1)

    assert [f.channel_ref.external_id for f in page] == ["c1", "c2"]
