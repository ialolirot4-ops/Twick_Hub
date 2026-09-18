from __future__ import annotations

import pytest

from twick_hub.infrastructure.downloads.progress_tracker import ProgressTracker
from twick_hub.infrastructure.downloads.retry_policy import RetryPolicy


def test_should_retry_true_below_max_attempts():
    policy = RetryPolicy(max_attempts=3)
    assert policy.should_retry(1) is True
    assert policy.should_retry(2) is True


def test_should_retry_false_at_max_attempts():
    policy = RetryPolicy(max_attempts=3)
    assert policy.should_retry(3) is False
    assert policy.should_retry(4) is False


def test_delay_for_grows_exponentially():
    policy = RetryPolicy(base_delay_seconds=1.0, max_delay_seconds=100.0)
    assert policy.delay_for(1) == pytest.approx(1.0)
    assert policy.delay_for(2) == pytest.approx(2.0)
    assert policy.delay_for(3) == pytest.approx(4.0)
    assert policy.delay_for(4) == pytest.approx(8.0)


def test_delay_for_caps_at_max_delay():
    policy = RetryPolicy(base_delay_seconds=1.0, max_delay_seconds=5.0)
    assert policy.delay_for(10) == pytest.approx(5.0)


def test_max_attempts_below_one_rejected():
    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=0)


def test_negative_base_delay_rejected():
    with pytest.raises(ValueError):
        RetryPolicy(base_delay_seconds=-1.0)


def test_progress_tracker_reports_percentage_for_known_total():
    tracker = ProgressTracker()
    tracker.start("job-1", total_segments=4)
    assert tracker.progress_of("job-1") == 0.0

    tracker.advance("job-1")
    assert tracker.progress_of("job-1") == pytest.approx(25.0)

    tracker.advance("job-1", by=3)
    assert tracker.progress_of("job-1") == pytest.approx(100.0)


def test_progress_tracker_never_exceeds_100():
    tracker = ProgressTracker()
    tracker.start("job-1", total_segments=2)
    tracker.advance("job-1", by=5)
    assert tracker.progress_of("job-1") == 100.0


def test_progress_tracker_unknown_job_returns_zero():
    tracker = ProgressTracker()
    assert tracker.progress_of("nope") == 0.0


def test_progress_tracker_unbounded_total_returns_zero_percent_but_tracks_count():
    tracker = ProgressTracker()
    tracker.start("live-job", total_segments=None)
    tracker.advance("live-job", by=7)

    assert tracker.progress_of("live-job") == 0.0
    assert tracker.segments_completed_of("live-job") == 7


def test_progress_tracker_finish_clears_state():
    tracker = ProgressTracker()
    tracker.start("job-1", total_segments=2)
    tracker.advance("job-1")
    tracker.finish("job-1")

    assert tracker.progress_of("job-1") == 0.0
    assert tracker.segments_completed_of("job-1") == 0
