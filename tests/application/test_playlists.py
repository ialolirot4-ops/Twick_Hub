import pytest

from tests.application.fakes import InMemoryPlaylistRepository
from twitchlink_next.application.playlists import (
    AddMediaToPlaylistUseCase,
    CreatePlaylistUseCase,
    PlaylistNotFoundError,
)
from twitchlink_next.domain.enums import MediaKind, Platform
from twitchlink_next.domain.value_objects import Media, PlatformRef

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
