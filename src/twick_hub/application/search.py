"""Unified search use case.

Backs the "All / Twitch / Kick" filter tabs built as mocks in FASE 2's
SearchPage.qml — this is what will actually drive them once a platform
adapter exists (FASE 4b/5).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from twick_hub.application.platform_registry import PlatformRegistry
from twick_hub.domain.enums import Platform
from twick_hub.domain.identity import Channel
from twick_hub.domain.protocols import ChannelDirectory


@dataclass(frozen=True, slots=True)
class SearchContentUseCase:
    """One ``ChannelDirectory`` per supported platform. A platform simply
    absent from this mapping is treated as unavailable, not an error —
    the same non-mandatory-protocol philosophy as domain/protocols.py.
    """

    directories: dict[Platform, ChannelDirectory]

    @classmethod
    def from_registry(cls, registry: PlatformRegistry) -> SearchContentUseCase:
        """Master Plan §43 (FASE 6, "unified search"): builds the same
        mapping from a ``PlatformRegistry`` instead of the caller
        assembling ``{Platform: ChannelDirectory}`` by hand. The
        ``directories=`` constructor is unchanged — existing callers and
        tests keep working as-is."""
        return cls(directories=registry.channel_directories)

    async def execute(self, query: str, platform: Platform | None = None) -> list[Channel]:
        if platform is not None:
            if platform not in self.directories:
                return []
            targets = [self.directories[platform]]
        else:
            targets = list(self.directories.values())

        results = await asyncio.gather(*(directory.find_channel(query) for directory in targets))
        return [channel for channel in results if channel is not None]
