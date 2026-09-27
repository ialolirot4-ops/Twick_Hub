from __future__ import annotations

from datetime import datetime

import pytest

from tests.application.fakes import (
    FakeChannelDirectory,
    FakeLiveStreamProvider,
    InMemoryFavoriteRepository,
    make_channel,
)
from twick_hub.application.favorites import (
    AddFavoriteUseCase,
    GetFavoritesLiveStateUseCase,
    ListFavoritesUseCase,
    RemoveFavoriteUseCase,
    ReorderFavoritesUseCase,
    UpdateFavoriteSettingsUseCase,
)
from twick_hub.application.platform_registry import PlatformAdapters, PlatformRegistry
from twick_hub.domain.content import Stream
from twick_hub.domain.enums import Platform
from twick_hub.domain.value_objects import PlatformRef


@pytest.fixture
def directory() -> FakeChannelDirectory:
    directory = FakeChannelDirectory()
    directory.add(make_channel("123", "northernlion", Platform.TWITCH))
    directory.add(make_channel("456", "someone", Platform.KICK))
    return directory


@pytest.fixture
def registry(directory: FakeChannelDirectory) -> PlatformRegistry:
    return PlatformRegistry(
        {
            Platform.TWITCH: PlatformAdapters(channel_directory=directory),
            Platform.KICK: PlatformAdapters(channel_directory=directory),
        }
    )


async def test_add_favorite_saves_it(registry):
    favorites = InMemoryFavoriteRepository()
    use_case = AddFavoriteUseCase(registry=registry, favorites=favorites)

    favorite = await use_case.execute(PlatformRef(platform=Platform.TWITCH, external_id="123"))

    assert favorite.channel_ref.external_id == "123"
    assert await favorites.list_all() == [favorite]


async def test_add_favorite_supports_kick_too(registry):
    """Master Plan §46: Favorites must support Twitch + Kick, not just
    whichever single ChannelDirectory a caller happened to inject."""
    favorites = InMemoryFavoriteRepository()
    use_case = AddFavoriteUseCase(registry=registry, favorites=favorites)

    favorite = await use_case.execute(PlatformRef(platform=Platform.KICK, external_id="456"))

    assert favorite.channel_ref.platform == Platform.KICK


async def test_add_favorite_twice_returns_the_existing_one(registry):
    favorites = InMemoryFavoriteRepository()
    use_case = AddFavoriteUseCase(registry=registry, favorites=favorites)
    ref = PlatformRef(platform=Platform.TWITCH, external_id="123")

    first = await use_case.execute(ref)
    second = await use_case.execute(ref)

    assert first.id == second.id
    assert len(await favorites.list_all()) == 1


async def test_add_favorite_for_unknown_channel_raises(registry):
    favorites = InMemoryFavoriteRepository()
    use_case = AddFavoriteUseCase(registry=registry, favorites=favorites)

    with pytest.raises(LookupError):
        await use_case.execute(PlatformRef(platform=Platform.TWITCH, external_id="does-not-exist"))


async def test_add_favorite_stores_quality_format_and_directory(registry):
    favorites = InMemoryFavoriteRepository()
    use_case = AddFavoriteUseCase(registry=registry, favorites=favorites)

    favorite = await use_case.execute(
        PlatformRef(platform=Platform.TWITCH, external_id="123"),
        preferred_quality="720p",
        preferred_format="mkv",
        download_directory="/home/user/Videos/NL",
    )

    assert favorite.preferred_quality == "720p"
    assert favorite.preferred_format == "mkv"
    assert favorite.download_directory == "/home/user/Videos/NL"


async def test_added_favorites_get_incrementing_positions(registry):
    favorites = InMemoryFavoriteRepository()
    use_case = AddFavoriteUseCase(registry=registry, favorites=favorites)

    first = await use_case.execute(PlatformRef(platform=Platform.TWITCH, external_id="123"))
    second = await use_case.execute(PlatformRef(platform=Platform.KICK, external_id="456"))

    assert first.position == 0
    assert second.position == 1


async def test_remove_favorite(registry):
    favorites = InMemoryFavoriteRepository()
    added = await AddFavoriteUseCase(registry=registry, favorites=favorites).execute(
        PlatformRef(platform=Platform.TWITCH, external_id="123")
    )

    await RemoveFavoriteUseCase(favorites=favorites).execute(added.id)

    assert await favorites.list_all() == []


async def test_list_favorites_reflects_the_repository(registry):
    favorites = InMemoryFavoriteRepository()
    await AddFavoriteUseCase(registry=registry, favorites=favorites).execute(
        PlatformRef(platform=Platform.TWITCH, external_id="123")
    )

    result = await ListFavoritesUseCase(favorites=favorites).execute()

    assert len(result) == 1


# --- update settings -------------------------------------------------


async def test_update_settings_changes_only_the_given_fields(registry):
    favorites = InMemoryFavoriteRepository()
    favorite = await AddFavoriteUseCase(registry=registry, favorites=favorites).execute(
        PlatformRef(platform=Platform.TWITCH, external_id="123"), preferred_quality="source"
    )

    updated = await UpdateFavoriteSettingsUseCase(favorites=favorites).execute(
        favorite.id, notify_on_live=False
    )

    assert updated.notify_on_live is False
    assert updated.preferred_quality == "source"  # untouched


async def test_update_settings_can_clear_a_field_to_none(registry):
    favorites = InMemoryFavoriteRepository()
    favorite = await AddFavoriteUseCase(registry=registry, favorites=favorites).execute(
        PlatformRef(platform=Platform.TWITCH, external_id="123"), preferred_quality="source"
    )

    updated = await UpdateFavoriteSettingsUseCase(favorites=favorites).execute(
        favorite.id, preferred_quality=None
    )

    assert updated.preferred_quality is None


async def test_update_settings_for_unknown_favorite_raises(registry):
    favorites = InMemoryFavoriteRepository()
    with pytest.raises(LookupError):
        await UpdateFavoriteSettingsUseCase(favorites=favorites).execute(
            "does-not-exist", notify_on_live=False
        )


# --- reorder -------------------------------------------------


async def test_reorder_applies_the_given_order(registry):
    favorites = InMemoryFavoriteRepository()
    use_case = AddFavoriteUseCase(registry=registry, favorites=favorites)
    a = await use_case.execute(PlatformRef(platform=Platform.TWITCH, external_id="123"))
    b = await use_case.execute(PlatformRef(platform=Platform.KICK, external_id="456"))

    reordered = await ReorderFavoritesUseCase(favorites=favorites).execute([b.id, a.id])

    assert [f.id for f in reordered] == [b.id, a.id]
    assert [f.id for f in await favorites.list_all()] == [b.id, a.id]


async def test_reorder_keeps_favorites_missing_from_the_list_in_place(registry):
    favorites = InMemoryFavoriteRepository()
    use_case = AddFavoriteUseCase(registry=registry, favorites=favorites)
    a = await use_case.execute(PlatformRef(platform=Platform.TWITCH, external_id="123"))
    b = await use_case.execute(PlatformRef(platform=Platform.KICK, external_id="456"))

    # only reorders `a`; `b` isn't mentioned and must not be dropped
    result = await ReorderFavoritesUseCase(favorites=favorites).execute([a.id])

    assert {f.id for f in result} == {a.id, b.id}


# --- live state -------------------------------------------------


async def test_live_state_reports_live_and_offline_favorites(registry):
    favorites = InMemoryFavoriteRepository()
    use_case = AddFavoriteUseCase(registry=registry, favorites=favorites)
    twitch_ref = PlatformRef(platform=Platform.TWITCH, external_id="123")
    kick_ref = PlatformRef(platform=Platform.KICK, external_id="456")
    live_favorite = await use_case.execute(twitch_ref)
    offline_favorite = await use_case.execute(kick_ref)

    live_ref = live_favorite.channel_ref
    stream = Stream(
        ref=PlatformRef(platform=Platform.TWITCH, external_id="s1"),
        channel_ref=live_ref,
        title="live!",
        category=None,
        started_at=datetime(2026, 1, 1),
        viewer_count=10,
    )
    live_provider = FakeLiveStreamProvider(streams={live_ref.external_id: stream})
    registry_with_live = PlatformRegistry(
        {
            Platform.TWITCH: PlatformAdapters(
                channel_directory=registry.get_platform(Platform.TWITCH).channel_directory,
                live_stream_provider=live_provider,
            ),
            Platform.KICK: PlatformAdapters(
                channel_directory=registry.get_platform(Platform.KICK).channel_directory
            ),
        }
    )

    states = await GetFavoritesLiveStateUseCase(
        favorites=favorites, registry=registry_with_live
    ).execute()

    by_id = {state.favorite.id: state for state in states}
    assert by_id[live_favorite.id].is_live is True
    assert by_id[offline_favorite.id].is_live is False


async def test_live_state_for_platform_with_no_live_provider_is_not_live(registry):
    """Kick (today) has no LiveStreamProvider at all — must report "not
    live," never raise, same philosophy as PlatformRegistry itself."""
    favorites = InMemoryFavoriteRepository()
    favorite = await AddFavoriteUseCase(registry=registry, favorites=favorites).execute(
        PlatformRef(platform=Platform.KICK, external_id="456")
    )

    states = await GetFavoritesLiveStateUseCase(favorites=favorites, registry=registry).execute()

    assert states[0].favorite.id == favorite.id
    assert states[0].is_live is False
