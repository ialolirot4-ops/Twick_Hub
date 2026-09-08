from dataclasses import FrozenInstanceError

import pytest

from twick_hub.domain.collections import Playlist
from twick_hub.domain.downloads import Download, DownloadJob
from twick_hub.domain.enums import MediaKind, Platform
from twick_hub.domain.value_objects import Media, PlatformRef

_MEDIA = Media(
    kind=MediaKind.VIDEO,
    ref=PlatformRef(platform=Platform.TWITCH, external_id="v1"),
    title="Some VOD",
)


def test_download_rejects_out_of_range_progress():
    with pytest.raises(ValueError, match="progress_percent"):
        Download(
            media=_MEDIA,
            destination_path="/tmp/out.mp4",
            quality_label="best",
            progress_percent=150,
        )


def test_download_generates_a_unique_id_by_default():
    a = Download(media=_MEDIA, destination_path="/tmp/a.mp4", quality_label="best")
    b = Download(media=_MEDIA, destination_path="/tmp/b.mp4", quality_label="best")
    assert a.id != b.id


def test_download_is_immutable():
    download = Download(media=_MEDIA, destination_path="/tmp/a.mp4", quality_label="best")
    with pytest.raises(FrozenInstanceError):
        download.progress_percent = 50.0  # type: ignore[misc]


def test_download_job_rejects_zero_attempt_number():
    with pytest.raises(ValueError, match="attempt_number"):
        DownloadJob(download_id="abc", attempt_number=0)


def test_playlist_with_item_added_returns_a_new_instance():
    playlist = Playlist(name="Highlights")
    updated = playlist.with_item_added(_MEDIA)

    assert playlist.items == ()  # original untouched
    assert len(updated.items) == 1
    assert updated.items[0].media == _MEDIA
    assert updated.items[0].position == 0
    assert updated is not playlist


def test_playlist_with_item_added_appends_at_the_next_position():
    playlist = Playlist(name="Highlights").with_item_added(_MEDIA).with_item_added(_MEDIA)
    assert [item.position for item in playlist.items] == [0, 1]
