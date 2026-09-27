from dataclasses import FrozenInstanceError

import pytest

from twick_hub.domain.collections import Playlist
from twick_hub.domain.downloads import Download, DownloadJob
from twick_hub.domain.enums import MediaKind, Platform
from twick_hub.domain.value_objects import Duration, Media, PlatformRef

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


# --- FASE 12: rename, remove, reorder, export/import ------------------------

_MEDIA_2 = Media(
    kind=MediaKind.CLIP,
    ref=PlatformRef(platform=Platform.KICK, external_id="c1"),
    title="A clip",
    channel_ref=PlatformRef(platform=Platform.KICK, external_id="chan1"),
    thumbnail_url="https://example.invalid/thumb.jpg",
    duration=Duration(total_seconds=90),
)


def test_playlist_renamed_returns_a_new_instance_with_the_new_name():
    playlist = Playlist(name="Highlights")

    renamed = playlist.renamed("Best of 2026")

    assert playlist.name == "Highlights"  # original untouched
    assert renamed.name == "Best of 2026"
    assert renamed.id == playlist.id  # same playlist, not a new one


def test_playlist_with_item_removed_closes_the_position_gap():
    playlist = (
        Playlist(name="H").with_item_added(_MEDIA).with_item_added(_MEDIA_2).with_item_added(_MEDIA)
    )
    middle_id = playlist.items[1].id

    updated = playlist.with_item_removed(middle_id)

    assert [item.media for item in updated.items] == [_MEDIA, _MEDIA]
    assert [item.position for item in updated.items] == [0, 1]
    assert len(playlist.items) == 3  # original untouched


def test_playlist_with_item_removed_unknown_id_raises():
    playlist = Playlist(name="H").with_item_added(_MEDIA)
    with pytest.raises(ValueError, match="no item"):
        playlist.with_item_removed("does-not-exist")


def test_playlist_with_items_reordered_renumbers_positions_to_match():
    playlist = Playlist(name="H").with_item_added(_MEDIA).with_item_added(_MEDIA_2)
    first_id, second_id = (item.id for item in playlist.items)

    reordered = playlist.with_items_reordered([second_id, first_id])

    assert [item.id for item in reordered.items] == [second_id, first_id]
    assert [item.position for item in reordered.items] == [0, 1]


@pytest.mark.parametrize(
    "bad_order_fn",
    [
        lambda ids: ids[:-1],  # missing one
        lambda ids: [*ids, "extra"],  # an id from nowhere
        lambda ids: [ids[0], ids[0]],  # duplicate
        lambda ids: list(reversed(ids)) + ["x"],  # wrong length, reversed
    ],
)
def test_playlist_with_items_reordered_rejects_anything_but_an_exact_permutation(bad_order_fn):
    playlist = Playlist(name="H").with_item_added(_MEDIA).with_item_added(_MEDIA_2)
    ids = [item.id for item in playlist.items]

    with pytest.raises(ValueError):
        playlist.with_items_reordered(bad_order_fn(ids))


def test_playlist_with_items_reordered_on_an_empty_playlist_accepts_the_empty_list():
    playlist = Playlist(name="Empty")
    assert playlist.with_items_reordered([]).items == ()


def test_playlist_export_then_import_round_trips_name_and_media():
    playlist = Playlist(name="Highlights").with_item_added(_MEDIA).with_item_added(_MEDIA_2)

    exported = playlist.to_export_dict()
    imported = Playlist.from_export_dict(exported)

    assert imported.name == "Highlights"
    assert [item.media for item in imported.items] == [_MEDIA, _MEDIA_2]
    assert imported.id != playlist.id  # a re-import is a new playlist, not the same one
    assert [item.id for item in imported.items] != [item.id for item in playlist.items]


def test_playlist_export_dict_has_no_ids_or_timestamps():
    playlist = Playlist(name="Highlights").with_item_added(_MEDIA)
    exported = playlist.to_export_dict()

    assert exported == {
        "name": "Highlights",
        "items": [
            {
                "kind": "clip" if _MEDIA.kind == MediaKind.CLIP else _MEDIA.kind.value,
                "platform": _MEDIA.ref.platform.value,
                "external_id": _MEDIA.ref.external_id,
                "title": _MEDIA.title,
                "channel_platform": None,
                "channel_external_id": None,
                "thumbnail_url": None,
                "duration_seconds": None,
            }
        ],
    }


def test_playlist_import_accepts_a_name_override():
    playlist = Playlist(name="Original").with_item_added(_MEDIA)
    exported = playlist.to_export_dict()

    imported = Playlist.from_export_dict(exported, name="Copy of Original")

    assert imported.name == "Copy of Original"


def test_playlist_export_preserves_channel_and_duration_when_present():
    playlist = Playlist(name="Clips").with_item_added(_MEDIA_2)
    exported = playlist.to_export_dict()

    imported = Playlist.from_export_dict(exported)

    assert imported.items[0].media.channel_ref == _MEDIA_2.channel_ref
    assert imported.items[0].media.duration == _MEDIA_2.duration
    assert imported.items[0].media.thumbnail_url == _MEDIA_2.thumbnail_url


@pytest.mark.parametrize(
    "malformed",
    [
        {},  # missing everything
        {"name": "X"},  # missing items
        {"name": "X", "items": [{}]},  # item missing required fields
        {
            "name": "X",
            "items": [
                {"kind": "not-a-real-kind", "platform": "twitch", "external_id": "1", "title": "t"}
            ],
        },
        {"name": "X", "items": "not-a-list"},
    ],
)
def test_playlist_from_export_dict_rejects_malformed_data_with_a_clear_error(malformed):
    with pytest.raises(ValueError, match="malformed playlist export data"):
        Playlist.from_export_dict(malformed)
