from twick_hub.domain.enums import Platform
from twick_hub.domain.value_objects import PlatformRef
from twick_hub.infrastructure.twitch.gql.mappers import (
    map_channel,
    map_clip,
    map_stream,
    map_video,
)

_USER_FIELDS = {
    "id": "123",
    "login": "northernlion",
    "displayName": "NorthernLion",
    "profileImageURL": "https://example.invalid/avatar.png",
    "createdAt": "2011-06-16T00:00:00Z",
}


def test_map_channel_offline():
    data = {
        **_USER_FIELDS,
        "roles": {"isPartner": True, "isAffiliate": False},
        "followers": {"totalCount": 900000},
        "stream": None,
    }

    channel = map_channel(data)

    assert channel.ref.platform == Platform.TWITCH
    assert channel.ref.external_id == "123"
    assert channel.user.username == "northernlion"
    assert channel.user.display_name == "NorthernLion"
    assert channel.is_live is False
    assert channel.stream_title is None
    assert channel.follower_count == 900000
    assert channel.is_verified_or_partner is True


def test_map_channel_live():
    data = {
        **_USER_FIELDS,
        "roles": {"isPartner": False, "isAffiliate": True},
        "followers": {"totalCount": 100},
        "stream": {
            "id": "456",
            "title": "Slay the Spire ranked run",
            "game": {"name": "Slay the Spire"},
            "previewImageURL": "https://example.invalid/preview.png",
            "createdAt": "2026-09-05T10:00:00Z",
            "viewersCount": 4200,
        },
    }

    channel = map_channel(data)

    assert channel.is_live is True
    assert channel.stream_title == "Slay the Spire ranked run"
    assert channel.category == "Slay the Spire"
    assert channel.is_verified_or_partner is True  # affiliate also counts


def test_map_channel_with_missing_optional_fields_uses_safe_defaults():
    data = {"id": "789", "login": "someone", "roles": {}, "followers": {}, "stream": None}

    channel = map_channel(data)

    assert channel.user.display_name == "someone"  # falls back to login
    assert channel.follower_count is None
    assert channel.is_verified_or_partner is False


def test_map_stream_returns_none_when_offline():
    channel_ref = PlatformRef(platform=Platform.TWITCH, external_id="123")
    assert map_stream({"stream": None}, channel_ref) is None


def test_map_video():
    data = {
        "id": "999",
        "title": "Full playthrough",
        "game": {"name": "Balatro"},
        "previewThumbnailURL": "https://example.invalid/thumb.png",
        "owner": {**_USER_FIELDS},
        "lengthSeconds": 7200,
        "createdAt": "2026-09-01T00:00:00Z",
        "publishedAt": "2026-09-01T01:00:00Z",
        "viewCount": 15000,
    }

    video = map_video(data)

    assert video.ref.external_id == "999"
    assert video.channel_ref.external_id == "123"
    assert video.duration.total_seconds == 7200
    assert video.view_count == 15000
    assert video.is_subscriber_only is False


def test_map_clip():
    data = {
        "id": "clip1",
        "title": "Clutch moment",
        "game": {"name": "Balatro"},
        "thumbnailURL": "https://example.invalid/clip-thumb.png",
        "slug": "clip1",
        "broadcaster": {**_USER_FIELDS},
        "curator": {**_USER_FIELDS, "id": "321", "login": "someviewer"},
        "durationSeconds": 30,
        "createdAt": "2026-09-04T00:00:00Z",
        "viewCount": 500,
    }

    clip = map_clip(data)

    assert clip.ref.external_id == "clip1"
    assert clip.channel_ref.external_id == "123"
    assert clip.creator.username == "someviewer"
    assert clip.duration.total_seconds == 30
