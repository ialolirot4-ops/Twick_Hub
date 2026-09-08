"""Enforces the real EventSub cost ceiling for a user access token
(config.py). ``max_channels`` is 5 — floor(10 / 2) — not an approximation:
each channel needs both ``stream.online`` and ``stream.offline``
(SUBSCRIPTION_TYPES_PER_CHANNEL), at cost 1 each, against a total budget
of 10.
"""

from __future__ import annotations

from twick_hub.domain.value_objects import PlatformRef
from twick_hub.infrastructure.twitch.eventsub.config import (
    COST_PER_SUBSCRIPTION,
    MAX_TOTAL_COST_USER_TOKEN,
    SUBSCRIPTION_TYPES_PER_CHANNEL,
)
from twick_hub.infrastructure.twitch.eventsub.errors import CapacityExceededError

_COST_PER_CHANNEL = COST_PER_SUBSCRIPTION * SUBSCRIPTION_TYPES_PER_CHANNEL


class CapacityGovernor:
    def __init__(self) -> None:
        self._reserved: set[PlatformRef] = set()

    @property
    def used_cost(self) -> int:
        return len(self._reserved) * _COST_PER_CHANNEL

    @property
    def max_channels(self) -> int:
        return MAX_TOTAL_COST_USER_TOKEN // _COST_PER_CHANNEL

    @property
    def remaining_channel_slots(self) -> int:
        return self.max_channels - len(self._reserved)

    def has_room_for(self, channel_ref: PlatformRef) -> bool:
        if channel_ref in self._reserved:
            return True  # already reserved — re-subscribing costs nothing new
        return self.used_cost + _COST_PER_CHANNEL <= MAX_TOTAL_COST_USER_TOKEN

    def reserve(self, channel_ref: PlatformRef) -> None:
        if channel_ref in self._reserved:
            return
        if not self.has_room_for(channel_ref):
            raise CapacityExceededError(
                f"Adding {channel_ref.external_id!r} would exceed the EventSub cost "
                f"budget ({self.used_cost}/{MAX_TOTAL_COST_USER_TOKEN} used, "
                f"{_COST_PER_CHANNEL} needed). Max {self.max_channels} channels with a "
                f"single user token — see docs/risk-register.md RISK-TWITCH-01."
            )
        self._reserved.add(channel_ref)

    def release(self, channel_ref: PlatformRef) -> None:
        self._reserved.discard(channel_ref)
