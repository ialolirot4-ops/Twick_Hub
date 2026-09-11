from twick_hub.domain.enums import Platform
from twick_hub.infrastructure.kick.mappers import map_channel, map_live_stream, map_user

_CHANNEL_OFFLINE = {
    "broadcaster_user_id": 123456,
    "slug": "xqc",
    "stream_title": "LIVE NOW",
    "channel_description": "Welcome to my channel!",
    "category": {"id": 1, "name": "Just Chatting", "thumbnail": "https://example.invalid/t.png"},
    "stream": None,
}

_LIVESTREAM = {
    "broadcaster_user_id": 123456,
    "channel_id": 1,
    "slug": "xqc",
    "stream_title": "Ranked run",
    "category": {"id": 2, "name": "Balatro", "slug": "balatro"},
    "language": "en",
    "has_mature_content": False,
    "viewer_count": 4200,
    "started_at": "2026-09-05T10:00:00+00:00",
    "thumbnail": "https://example.invalid/thumb.png",
}


def test_map_channel_offline():
    channel = map_channel(_CHANNEL_OFFLINE)
    assert channel.ref.platform == Platform.KICK
    assert channel.ref.external_id == "123456"
    assert channel.user.username == "xqc"
    assert channel.is_live is False
    assert channel.category == "Just Chatting"


def test_map_channel_live():
    live = {**_CHANNEL_OFFLINE, "stream": {"id": 1}}
    channel = map_channel(live)
    assert channel.is_live is True


def test_map_channel_never_guesses_partner_status():
    """Kick's official Channel resource doesn't expose a verified/partner
    flag — this must stay False, not be inferred from anything else."""
    channel = map_channel(_CHANNEL_OFFLINE)
    assert channel.is_verified_or_partner is False


def test_map_live_stream():
    stream = map_live_stream(_LIVESTREAM)
    assert stream.ref.platform == Platform.KICK
    assert stream.ref.external_id == "123456"
    assert stream.title == "Ranked run"
    assert stream.category == "Balatro"
    assert stream.viewer_count == 4200


def test_map_user_with_minimal_fields():
    data = {"user_id": 7, "name": "someone", "profile_picture": "https://x.invalid/a.png"}
    user = map_user(data)
    assert user.ref.external_id == "7"
    assert user.username == "someone"
    assert user.avatar_url == "https://x.invalid/a.png"
