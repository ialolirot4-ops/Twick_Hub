from __future__ import annotations

from dataclasses import replace

from sqlalchemy.orm import sessionmaker

from twick_hub.domain.enums import Platform
from twick_hub.domain.identity import Channel, User
from twick_hub.domain.value_objects import PlatformRef
from twick_hub.infrastructure.persistence.channel_repository import SqlChannelRepository


def _channel(username: str = "northernlion") -> Channel:
    ref = PlatformRef(platform=Platform.TWITCH, external_id="c1")
    return Channel(
        ref=ref,
        user=User(ref=ref, username=username, display_name=username.title(), avatar_url=None),
        is_live=False,
        follower_count=1000,
    )


async def test_get_returns_none_for_missing_channel(session_factory: sessionmaker):
    repo = SqlChannelRepository(session_factory)
    assert await repo.get(PlatformRef(platform=Platform.TWITCH, external_id="nope")) is None


async def test_save_then_get_round_trips_every_field(session_factory: sessionmaker):
    repo = SqlChannelRepository(session_factory)
    channel = replace(
        _channel(),
        is_live=True,
        stream_title="Live now",
        category="Just Chatting",
        is_verified_or_partner=True,
    )

    await repo.save(channel)
    fetched = await repo.get(channel.ref)

    assert fetched == channel


async def test_save_upserts_by_platform_ref(session_factory: sessionmaker):
    repo = SqlChannelRepository(session_factory)
    channel = _channel()
    await repo.save(channel)

    updated = replace(channel, is_live=True, follower_count=2000)
    await repo.save(updated)

    fetched = await repo.get(channel.ref)
    assert fetched == updated


async def test_channels_on_different_platforms_with_same_external_id_are_distinct(
    session_factory: sessionmaker,
):
    repo = SqlChannelRepository(session_factory)
    twitch_ref = PlatformRef(platform=Platform.TWITCH, external_id="c1")
    kick_ref = PlatformRef(platform=Platform.KICK, external_id="c1")
    twitch_channel = Channel(
        ref=twitch_ref, user=User(ref=twitch_ref, username="a", display_name="A")
    )
    kick_channel = Channel(ref=kick_ref, user=User(ref=kick_ref, username="b", display_name="B"))

    await repo.save(twitch_channel)
    await repo.save(kick_channel)

    assert await repo.get(twitch_ref) == twitch_channel
    assert await repo.get(kick_ref) == kick_channel
