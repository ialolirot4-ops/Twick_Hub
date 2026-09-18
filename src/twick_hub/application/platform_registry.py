"""Platform Layer (Master Plan §43, FASE 6): the one place Application
asks "does this platform support X" and "give me its Y adapter" instead
of every use case threading its own ``dict[Platform, SomeProtocol]``
through by hand — which is exactly what ``application/search.py``'s
``SearchContentUseCase`` did pre-FASE 6 (its ``directories=`` constructor
is unchanged; ``SearchContentUseCase.from_registry()`` now builds that
same mapping from a ``PlatformRegistry`` instead).

A platform simply missing an adapter is treated as "not supported," never
as an error to work around — the same non-mandatory-protocol philosophy
domain/protocols.py already documents, and which docs/kick-audit.md's
findings (no official VOD/Clips on Kick) depend on.

Nothing here talks to Qt, HTTP, or a real Twitch/Kick endpoint — those
live in Infrastructure (FASE 4a-5) and get assembled into a
``PlatformAdapters`` per platform by whichever phase wires the DI
container (see docs/architecture-decisions.md's FASE 6 entry for why
that wiring itself is out of this phase's scope).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from twick_hub.domain.content import Stream
from twick_hub.domain.enums import Platform
from twick_hub.domain.identity import Channel
from twick_hub.domain.protocols import (
    AccountProvider,
    ChannelDirectory,
    ClipProvider,
    LiveMonitor,
    LiveStreamProvider,
    PlaybackResolver,
    VideoProvider,
)
from twick_hub.domain.value_objects import Media, PlatformRef, PlaybackSource

# --- adapters + capabilities -------------------------------------------------


@dataclass(frozen=True, slots=True)
class PlatformAdapters:
    """Whichever adapters a platform's FASE 4/5 infrastructure actually
    implements, bundled together. Every field is optional — see this
    module's docstring; a platform (Kick, today) can leave VideoProvider/
    ClipProvider/PlaybackResolver unset rather than faking them.
    """

    account: AccountProvider | None = None
    channel_directory: ChannelDirectory | None = None
    live_stream_provider: LiveStreamProvider | None = None
    video_provider: VideoProvider | None = None
    clip_provider: ClipProvider | None = None
    playback_resolver: PlaybackResolver | None = None
    live_monitor: LiveMonitor | None = None


@dataclass(frozen=True, slots=True)
class PlatformCapabilities:
    """What a platform can actually do, derived from ``PlatformAdapters``
    — never hand-maintained, so it can't drift from what's really wired.
    Presentation-layer phases that connect real data (FASE 9+) read this
    to hide/disable features the current platform doesn't support
    (Master Plan §43: "La UI debe ocultar/deshabilitar funciones no
    soportadas").
    """

    has_account: bool
    can_search_channels: bool
    has_live: bool
    has_videos: bool
    has_clips: bool
    has_playback: bool
    has_live_monitor: bool

    @classmethod
    def from_adapters(cls, adapters: PlatformAdapters) -> PlatformCapabilities:
        return cls(
            has_account=adapters.account is not None,
            can_search_channels=adapters.channel_directory is not None,
            has_live=adapters.live_stream_provider is not None,
            has_videos=adapters.video_provider is not None,
            has_clips=adapters.clip_provider is not None,
            has_playback=adapters.playback_resolver is not None,
            has_live_monitor=adapters.live_monitor is not None,
        )

    def as_dict(self) -> dict[str, bool]:
        """Plain bool mapping, camelCase-keyed — a future presentation
        bridge (not this phase) can hand this straight to QML without
        depending on this dataclass directly."""
        return {
            "hasAccount": self.has_account,
            "canSearchChannels": self.can_search_channels,
            "hasLive": self.has_live,
            "hasVideos": self.has_videos,
            "hasClips": self.has_clips,
            "hasPlayback": self.has_playback,
            "hasLiveMonitor": self.has_live_monitor,
        }


# --- errors -------------------------------------------------


class UnknownPlatformError(Exception):
    """Raised by ``get_platform``/unified dispatch for a ``Platform`` the
    registry was never given adapters for at all. Distinct from
    ``UnsupportedCapabilityError`` (platform is registered, but the
    specific adapter is absent) and from returning ``None``/``[]``
    (used where absence is a normal, expected outcome — e.g. live
    status)."""

    def __init__(self, platform: Platform) -> None:
        super().__init__(f"no adapters registered for platform: {platform}")
        self.platform = platform


class UnsupportedCapabilityError(Exception):
    """Raised when unified dispatch is asked to do something the target
    platform's adapters don't support (e.g. resolving playback on a
    platform with no ``PlaybackResolver``)."""

    def __init__(self, platform: Platform, capability: str) -> None:
        super().__init__(f"{platform} has no {capability}")
        self.platform = platform
        self.capability = capability


# --- registry -------------------------------------------------


@dataclass(frozen=True, slots=True)
class PlatformRegistry:
    """Master Plan §43: "Debe permitir get_platform('twitch') /
    get_platform('kick')". Built once from a ``PlatformAdapters`` per
    supported ``Platform`` (see this module's docstring re: DI wiring).
    """

    _adapters: dict[Platform, PlatformAdapters] = field(default_factory=dict)

    def get_platform(self, platform: Platform) -> PlatformAdapters:
        try:
            return self._adapters[platform]
        except KeyError:
            raise UnknownPlatformError(platform) from None

    def is_registered(self, platform: Platform) -> bool:
        return platform in self._adapters

    def capabilities_for(self, platform: Platform) -> PlatformCapabilities:
        return PlatformCapabilities.from_adapters(self.get_platform(platform))

    def all_capabilities(self) -> dict[Platform, PlatformCapabilities]:
        return {
            platform: PlatformCapabilities.from_adapters(adapters)
            for platform, adapters in self._adapters.items()
        }

    @property
    def channel_directories(self) -> dict[Platform, ChannelDirectory]:
        """Unified search (Master Plan §43): the mapping
        ``SearchContentUseCase.from_registry()`` consumes — every
        registered platform that actually has a ``ChannelDirectory``."""
        return {
            platform: adapters.channel_directory
            for platform, adapters in self._adapters.items()
            if adapters.channel_directory is not None
        }

    async def get_channel(self, ref: PlatformRef) -> Channel:
        """Unified channels: routes to the right platform's
        ``ChannelDirectory`` by ``ref.platform``, so callers never branch
        on ``Platform`` themselves."""
        adapters = self.get_platform(ref.platform)
        if adapters.channel_directory is None:
            raise UnsupportedCapabilityError(ref.platform, "channel_directory")
        return await adapters.channel_directory.get_channel(ref)

    async def get_live_stream(self, channel_ref: PlatformRef) -> Stream | None:
        """Unified live: a platform with no ``LiveStreamProvider`` is
        treated as "definitely not live," not an error — same
        non-mandatory-protocol philosophy as domain/protocols.py."""
        adapters = self.get_platform(channel_ref.platform)
        if adapters.live_stream_provider is None:
            return None
        return await adapters.live_stream_provider.get_live_stream(channel_ref)

    async def resolve_playback(self, media: Media, quality: str) -> PlaybackSource:
        """Unified media: resolves a ``Media`` reference to a playable
        source via whichever platform's ``PlaybackResolver`` applies."""
        adapters = self.get_platform(media.ref.platform)
        if adapters.playback_resolver is None:
            raise UnsupportedCapabilityError(media.ref.platform, "playback_resolver")
        return await adapters.playback_resolver.resolve(media, quality)

    async def available_qualities(self, media: Media) -> list[str]:
        """Unified media: a platform with no ``PlaybackResolver`` simply
        has no known qualities, not an error."""
        adapters = self.get_platform(media.ref.platform)
        if adapters.playback_resolver is None:
            return []
        return await adapters.playback_resolver.available_qualities(media)
