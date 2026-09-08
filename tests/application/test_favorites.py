import pytest

from tests.application.fakes import FakeChannelDirectory, InMemoryFavoriteRepository, make_channel
from twick_hub.application.favorites import (
    AddFavoriteUseCase,
    ListFavoritesUseCase,
    RemoveFavoriteUseCase,
)
from twick_hub.domain.enums import Platform
from twick_hub.domain.value_objects import PlatformRef


@pytest.fixture
def directory() -> FakeChannelDirectory:
    directory = FakeChannelDirectory()
    directory.add(make_channel("123", "northernlion", Platform.TWITCH))
    return directory


async def test_add_favorite_saves_it(directory):
    favorites = InMemoryFavoriteRepository()
    use_case = AddFavoriteUseCase(channel_directory=directory, favorites=favorites)

    favorite = await use_case.execute(PlatformRef(platform=Platform.TWITCH, external_id="123"))

    assert favorite.channel_ref.external_id == "123"
    assert await favorites.list_all() == [favorite]


async def test_add_favorite_twice_returns_the_existing_one(directory):
    favorites = InMemoryFavoriteRepository()
    use_case = AddFavoriteUseCase(channel_directory=directory, favorites=favorites)
    ref = PlatformRef(platform=Platform.TWITCH, external_id="123")

    first = await use_case.execute(ref)
    second = await use_case.execute(ref)

    assert first.id == second.id
    assert len(await favorites.list_all()) == 1


async def test_add_favorite_for_unknown_channel_raises(directory):
    favorites = InMemoryFavoriteRepository()
    use_case = AddFavoriteUseCase(channel_directory=directory, favorites=favorites)

    with pytest.raises(LookupError):
        await use_case.execute(PlatformRef(platform=Platform.TWITCH, external_id="does-not-exist"))


async def test_remove_favorite(directory):
    favorites = InMemoryFavoriteRepository()
    added = await AddFavoriteUseCase(channel_directory=directory, favorites=favorites).execute(
        PlatformRef(platform=Platform.TWITCH, external_id="123")
    )

    await RemoveFavoriteUseCase(favorites=favorites).execute(added.id)

    assert await favorites.list_all() == []


async def test_list_favorites_reflects_the_repository(directory):
    favorites = InMemoryFavoriteRepository()
    await AddFavoriteUseCase(channel_directory=directory, favorites=favorites).execute(
        PlatformRef(platform=Platform.TWITCH, external_id="123")
    )

    result = await ListFavoritesUseCase(favorites=favorites).execute()

    assert len(result) == 1
