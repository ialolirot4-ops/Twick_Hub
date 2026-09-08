import pytest

from twick_hub.domain.enums import Platform
from twick_hub.domain.value_objects import PlatformRef
from twick_hub.infrastructure.twitch.eventsub.capacity import CapacityGovernor
from twick_hub.infrastructure.twitch.eventsub.errors import CapacityExceededError


def _ref(n: int) -> PlatformRef:
    return PlatformRef(platform=Platform.TWITCH, external_id=str(n))


def test_max_channels_is_five():
    """floor(10 / 2) — the real, documented ceiling (RISK-TWITCH-01),
    not an approximation."""
    assert CapacityGovernor().max_channels == 5


def test_reserving_five_channels_succeeds():
    governor = CapacityGovernor()
    for i in range(5):
        governor.reserve(_ref(i))
    assert governor.used_cost == 10
    assert governor.remaining_channel_slots == 0


def test_reserving_a_sixth_channel_raises():
    governor = CapacityGovernor()
    for i in range(5):
        governor.reserve(_ref(i))
    with pytest.raises(CapacityExceededError):
        governor.reserve(_ref(5))


def test_reserving_the_same_channel_twice_is_free():
    governor = CapacityGovernor()
    governor.reserve(_ref(1))
    governor.reserve(_ref(1))
    assert governor.used_cost == 2


def test_release_frees_a_slot():
    governor = CapacityGovernor()
    for i in range(5):
        governor.reserve(_ref(i))
    governor.release(_ref(0))
    governor.reserve(_ref(99))  # would have raised before releasing
    assert governor.used_cost == 10


def test_releasing_an_unreserved_channel_is_a_noop():
    governor = CapacityGovernor()
    governor.release(_ref(1))  # must not raise
    assert governor.used_cost == 0
