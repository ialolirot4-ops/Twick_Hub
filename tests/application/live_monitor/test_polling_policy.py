from __future__ import annotations

import pytest

from twick_hub.application.live_monitor.polling_policy import AdaptiveInterval, PollingConfig


def _policy(**overrides) -> AdaptiveInterval:
    config = PollingConfig(
        base_interval=60,
        max_quiet_interval=180,
        max_backoff_interval=900,
        jitter_ratio=0.1,
        **overrides,
    )
    return AdaptiveInterval(config, rng=lambda: 0.0)


def test_starts_at_the_base_interval():
    assert _policy().current_interval == 60


def test_quiet_polls_stretch_the_interval_only_after_the_threshold_and_up_to_the_ceiling():
    policy = _policy(quiet_polls_before_stretch=3, quiet_stretch_factor=2.0)

    for _ in range(2):
        policy.record_success(changed=False)
    assert policy.current_interval == 60  # not yet

    policy.record_success(changed=False)
    assert policy.current_interval == 120

    policy.record_success(changed=False)
    assert policy.current_interval == 180  # 240 clamped to the quiet ceiling
    policy.record_success(changed=False)
    assert policy.current_interval == 180


def test_a_change_snaps_back_to_base():
    policy = _policy(quiet_polls_before_stretch=1, quiet_stretch_factor=2.0)
    policy.record_success(changed=False)
    assert policy.current_interval == 120

    policy.record_success(changed=True)

    assert policy.current_interval == 60


def test_stretch_can_be_disabled_by_equal_base_and_ceiling():
    policy = AdaptiveInterval(PollingConfig(base_interval=900, max_quiet_interval=900))
    for _ in range(20):
        policy.record_success(changed=False)
    assert policy.current_interval == 900


def test_failures_back_off_exponentially_up_to_the_cap():
    policy = _policy()
    seen = []
    for _ in range(6):
        policy.record_failure()
        seen.append(policy.current_interval)

    assert seen == [120, 240, 480, 900, 900, 900]
    assert policy.consecutive_failures == 6


def test_retry_after_is_a_floor_never_undercut():
    policy = _policy()

    policy.record_failure(retry_after=500)

    assert policy.current_interval == 500  # more than the 120s backoff would give


def test_retry_after_smaller_than_backoff_does_not_shorten_it():
    policy = _policy()

    policy.record_failure(retry_after=5)

    assert policy.current_interval == 120


def test_absurd_retry_after_is_clamped():
    policy = _policy()

    policy.record_failure(retry_after=10_000_000)

    assert policy.current_interval == 3600


def test_first_success_after_failures_returns_to_base_even_if_unchanged():
    policy = _policy()
    policy.record_failure()
    policy.record_failure()

    policy.record_success(changed=False)

    assert policy.current_interval == 60
    assert policy.consecutive_failures == 0


def test_jitter_only_lengthens_the_delay():
    low = AdaptiveInterval(PollingConfig(base_interval=100, jitter_ratio=0.1), rng=lambda: 0.0)
    high = AdaptiveInterval(PollingConfig(base_interval=100, jitter_ratio=0.1), rng=lambda: 1.0)

    assert low.next_delay() == 100
    assert high.next_delay() == pytest.approx(110)


def test_reset_restores_a_fresh_state():
    policy = _policy()
    policy.record_failure()
    policy.reset()
    assert policy.current_interval == 60
    assert policy.consecutive_failures == 0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"base_interval": 0},
        {"base_interval": 60, "max_quiet_interval": 30},
        {"base_interval": 60, "max_backoff_interval": 30},
        {"quiet_stretch_factor": 0.5},
        {"backoff_factor": 0.5},
        {"quiet_polls_before_stretch": 0},
        {"jitter_ratio": 1.5},
        {"coalesce_seconds": -1},
    ],
)
def test_invalid_config_is_rejected(kwargs):
    with pytest.raises(ValueError):
        PollingConfig(**kwargs)
