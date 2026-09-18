from datetime import UTC, datetime

import pytest

from tests.application.fakes import (
    FakeAccountProvider,
    FakeChannelDirectory,
    FakeClipProvider,
    FakeLiveMonitor,
    FakeLiveStreamProvider,
    FakePlaybackResolver,
    FakeVideoProvider,
    make_channel,
)
from twick_hub.application.platform_registry import (
    PlatformAdapters,
    PlatformCapabilities,
    PlatformRegistry,
    UnknownPlatformError,
    UnsupportedCapabilityError,
)
from twick_hub.application.search import SearchContentUseCase
from twick_hub.domain.content import Stream
from twick_hub.domain.enums import MediaKind, Platform
from twick_hub.domain.value_objects import Media, PlatformRef


def _ref(platform: Platform, external_id: str = "c1") -> PlatformRef:
    return PlatformRef(platform=platform, external_id=external_id)


def _stream(channel_ref: PlatformRef) -> Stream:
    return Stream(
        ref=PlatformRef(platform=channel_ref.platform, external_id="s1"),
        channel_ref=channel_ref,
        title="live now",
        category=None,
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        viewer_count=42,
    )


def _full_twitch_adapters() -> PlatformAdapters:
    twitch_directory = FakeChannelDirectory()
    twitch_directory.add(make_channel("c1", "northernlion", Platform.TWITCH))
    live = FakeLiveStreamProvider()
    live.streams["c1"] = _stream(_ref(Platform.TWITCH))
    return PlatformAdapters(
        account=FakeAccountProvider(),
        channel_directory=twitch_directory,
        live_stream_provider=live,
        video_provider=FakeVideoProvider(),
        clip_provider=FakeClipProvider(),
        playback_resolver=FakePlaybackResolver(),
        live_monitor=FakeLiveMonitor(),
    )


def _kick_adapters_official_only() -> PlatformAdapters:
    """Mirrors docs/kick-audit.md: Kick's official API has no VOD/Clips,
    so those adapters stay unset rather than faked."""
    kick_directory = FakeChannelDirectory()
    kick_directory.add(make_channel("c1", "someone", Platform.KICK))
    return PlatformAdapters(
        account=FakeAccountProvider(),
        channel_directory=kick_directory,
    )


def _registry() -> PlatformRegistry:
    return PlatformRegistry(
        {
            Platform.TWITCH: _full_twitch_adapters(),
            Platform.KICK: _kick_adapters_official_only(),
        }
    )


# --- get_platform -------------------------------------------------


def test_get_platform_returns_registered_adapters():
    registry = _registry()
    assert registry.get_platform(Platform.TWITCH).channel_directory is not None


def test_get_platform_for_unregistered_platform_raises():
    registry = PlatformRegistry({Platform.TWITCH: _full_twitch_adapters()})
    with pytest.raises(UnknownPlatformError):
        registry.get_platform(Platform.KICK)


def test_is_registered():
    registry = PlatformRegistry({Platform.TWITCH: _full_twitch_adapters()})
    assert registry.is_registered(Platform.TWITCH) is True
    assert registry.is_registered(Platform.KICK) is False


# --- capabilities -------------------------------------------------


def test_capabilities_reflect_which_adapters_are_present():
    registry = _registry()

    twitch_caps = registry.capabilities_for(Platform.TWITCH)
    assert twitch_caps == PlatformCapabilities(
        has_account=True,
        can_search_channels=True,
        has_live=True,
        has_videos=True,
        has_clips=True,
        has_playback=True,
        has_live_monitor=True,
    )

    kick_caps = registry.capabilities_for(Platform.KICK)
    assert kick_caps == PlatformCapabilities(
        has_account=True,
        can_search_channels=True,
        has_live=False,
        has_videos=False,
        has_clips=False,
        has_playback=False,
        has_live_monitor=False,
    )


def test_all_capabilities_covers_every_registered_platform():
    registry = _registry()
    caps = registry.all_capabilities()
    assert set(caps.keys()) == {Platform.TWITCH, Platform.KICK}


def test_capabilities_as_dict_is_camel_case_bool_map():
    caps = PlatformCapabilities.from_adapters(_kick_adapters_official_only())
    assert caps.as_dict() == {
        "hasAccount": True,
        "canSearchChannels": True,
        "hasLive": False,
        "hasVideos": False,
        "hasClips": False,
        "hasPlayback": False,
        "hasLiveMonitor": False,
    }


# --- unified channels -------------------------------------------------


async def test_get_channel_dispatches_to_the_right_platform():
    registry = _registry()
    channel = await registry.get_channel(_ref(Platform.KICK))
    assert channel.ref.platform == Platform.KICK
    assert channel.user.username == "someone"


async def test_get_channel_for_platform_missing_directory_raises_unsupported():
    registry = PlatformRegistry({Platform.TWITCH: PlatformAdapters()})
    with pytest.raises(UnsupportedCapabilityError):
        await registry.get_channel(_ref(Platform.TWITCH))


async def test_get_channel_for_unregistered_platform_raises_unknown():
    registry = PlatformRegistry({})
    with pytest.raises(UnknownPlatformError):
        await registry.get_channel(_ref(Platform.TWITCH))


# --- unified live -------------------------------------------------


async def test_get_live_stream_dispatches_to_the_right_platform():
    registry = _registry()
    stream = await registry.get_live_stream(_ref(Platform.TWITCH))
    assert stream is not None
    assert stream.channel_ref.platform == Platform.TWITCH


async def test_get_live_stream_with_no_live_provider_returns_none_not_error():
    registry = _registry()
    result = await registry.get_live_stream(_ref(Platform.KICK))
    assert result is None


async def test_get_live_stream_with_provider_but_channel_not_live_returns_none():
    registry = _registry()
    result = await registry.get_live_stream(_ref(Platform.TWITCH, "not-live-channel"))
    assert result is None


# --- unified media -------------------------------------------------


def _media(platform: Platform) -> Media:
    return Media(kind=MediaKind.STREAM, ref=_ref(platform, "m1"), title="a stream")


async def test_resolve_playback_dispatches_to_the_right_platform():
    registry = _registry()
    source = await registry.resolve_playback(_media(Platform.TWITCH), quality="source")
    assert source.quality_label == "source"


async def test_resolve_playback_with_no_resolver_raises_unsupported():
    registry = _registry()
    with pytest.raises(UnsupportedCapabilityError):
        await registry.resolve_playback(_media(Platform.KICK), quality="source")


async def test_available_qualities_with_no_resolver_returns_empty_not_error():
    registry = _registry()
    qualities = await registry.available_qualities(_media(Platform.KICK))
    assert qualities == []


async def test_available_qualities_dispatches_to_the_right_platform():
    registry = _registry()
    qualities = await registry.available_qualities(_media(Platform.TWITCH))
    assert qualities == ["source", "720p", "480p"]


# --- unified search wiring -------------------------------------------------


def test_channel_directories_only_includes_platforms_with_a_directory():
    registry = PlatformRegistry(
        {
            Platform.TWITCH: _full_twitch_adapters(),
            Platform.KICK: PlatformAdapters(),  # no channel_directory
        }
    )
    assert set(registry.channel_directories.keys()) == {Platform.TWITCH}


async def test_search_content_use_case_from_registry_matches_manual_construction():
    registry = _registry()
    use_case = SearchContentUseCase.from_registry(registry)
    results = await use_case.execute("c1")
    assert {channel.ref.platform for channel in results} == {Platform.TWITCH, Platform.KICK}
