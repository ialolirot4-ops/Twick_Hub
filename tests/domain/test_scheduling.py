from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest

from twick_hub.domain.collections import Favorite, ScheduledDownload
from twick_hub.domain.enums import Platform, ScheduleOutcome, SchedulePhase, ScheduleTrigger
from twick_hub.domain.schedule_math import next_occurrence
from twick_hub.domain.scheduling import AutoDownloadRule, NotificationRule
from twick_hub.domain.value_objects import PlatformRef

CHANNEL = PlatformRef(platform=Platform.TWITCH, external_id="1")
# 2026-09-21 is a Monday.
MON_10 = datetime(2026, 9, 21, 10, 0)


def _at_time(**overrides) -> ScheduledDownload:
    fields = {"channel_ref": CHANNEL, "trigger": ScheduleTrigger.AT_TIME, "run_at": MON_10}
    return ScheduledDownload(**{**fields, **overrides})


# --- next_occurrence -------------------------------------------------------


def test_next_occurrence_is_strictly_after():
    assert next_occurrence(time(10, 0), (), MON_10) == datetime(2026, 9, 22, 10, 0)


def test_next_occurrence_later_the_same_day():
    assert next_occurrence(time(20, 0), (), MON_10) == datetime(2026, 9, 21, 20, 0)


def test_next_occurrence_respects_weekdays():
    friday = 4
    assert next_occurrence(time(20, 0), (friday,), MON_10) == datetime(2026, 9, 25, 20, 0)


def test_next_occurrence_wraps_to_next_week_for_the_same_weekday():
    monday = 0
    assert next_occurrence(time(9, 0), (monday,), MON_10) == datetime(2026, 9, 28, 9, 0)


def test_next_occurrence_raises_for_weekdays_outside_0_to_6():
    """No real caller can produce this (``ScheduledDownload`` validates its
    own ``weekdays`` — see below), but ``next_occurrence`` is a public,
    pure function in its own right and shouldn't silently loop forever or
    return a wrong date for a malformed input; it should say so."""
    with pytest.raises(ValueError, match="weekdays must be within 0..6"):
        next_occurrence(time(10, 0), (10,), MON_10)


# --- ScheduledDownload validation -------------------------------------------


def test_at_time_requires_run_at():
    with pytest.raises(ValueError):
        ScheduledDownload(channel_ref=CHANNEL, trigger=ScheduleTrigger.AT_TIME)


@pytest.mark.parametrize("trigger", [ScheduleTrigger.ON_NEXT_LIVE, ScheduleTrigger.RECURRING])
def test_event_triggers_reject_run_at_and_weekdays(trigger):
    with pytest.raises(ValueError):
        ScheduledDownload(channel_ref=CHANNEL, trigger=trigger, run_at=MON_10)
    with pytest.raises(ValueError):
        ScheduledDownload(channel_ref=CHANNEL, trigger=trigger, weekdays=(1,))


@pytest.mark.parametrize(
    "kwargs", [{"weekdays": (7,)}, {"window_seconds": 30}, {"max_attempts": 0}]
)
def test_invalid_fields_are_rejected(kwargs):
    with pytest.raises(ValueError):
        _at_time(**kwargs)


def test_the_fase_3_constructor_call_still_works():
    scheduled = ScheduledDownload(channel_ref=CHANNEL, trigger=ScheduleTrigger.RECURRING)
    assert scheduled.is_active and scheduled.priority == 0 and scheduled.download_id is None


# --- first due --------------------------------------------------------------


def test_one_shot_first_due_is_run_at():
    assert _at_time().with_first_due(MON_10 - timedelta(days=1)).next_due_at == MON_10


def test_event_triggers_have_no_due_time():
    item = ScheduledDownload(channel_ref=CHANNEL, trigger=ScheduleTrigger.ON_NEXT_LIVE)
    assert item.with_first_due(MON_10).next_due_at is None


def test_repeating_item_created_inside_todays_window_arms_immediately():
    item = _at_time(weekdays=(0, 1, 2, 3, 4, 5, 6), window_seconds=4 * 3600)

    armed = item.with_first_due(MON_10 + timedelta(hours=2))  # 12:00, window runs to 14:00

    assert armed.next_due_at == MON_10  # today's 10:00, not tomorrow's


def test_repeating_item_created_after_todays_window_waits_for_the_next_day():
    item = _at_time(weekdays=(0, 1, 2, 3, 4, 5, 6), window_seconds=4 * 3600)

    armed = item.with_first_due(MON_10 + timedelta(hours=5))  # 15:00, window closed at 14:00

    assert armed.next_due_at == MON_10 + timedelta(days=1)


# --- phase ------------------------------------------------------------------


def test_phase_walks_through_scheduled_waiting_expired():
    item = _at_time(window_seconds=3600).with_first_due(MON_10 - timedelta(days=1))

    assert item.phase(MON_10 - timedelta(minutes=1)) is SchedulePhase.SCHEDULED
    assert item.phase(MON_10) is SchedulePhase.WAITING_LIVE
    assert item.phase(MON_10 + timedelta(minutes=59)) is SchedulePhase.WAITING_LIVE
    assert item.phase(MON_10 + timedelta(hours=1)) is SchedulePhase.EXPIRED


def test_phase_running_and_disabled_take_precedence():
    item = _at_time().with_first_due(MON_10)
    assert item.begin_attempt("d1", MON_10).phase(MON_10) is SchedulePhase.RUNNING
    assert (
        ScheduledDownload(
            channel_ref=CHANNEL, trigger=ScheduleTrigger.RECURRING, is_active=False
        ).phase(MON_10)
        is SchedulePhase.DISABLED
    )


@pytest.mark.parametrize("trigger", [ScheduleTrigger.ON_NEXT_LIVE, ScheduleTrigger.RECURRING])
def test_event_triggers_are_always_waiting_for_a_go_live(trigger):
    item = ScheduledDownload(channel_ref=CHANNEL, trigger=trigger)
    assert item.phase(MON_10) is SchedulePhase.WAITING_LIVE


# --- attempts and finishing -------------------------------------------------


def test_begin_attempt_counts_and_records_the_trigger_time_only_when_a_download_started():
    item = _at_time()

    started = item.begin_attempt("d1", MON_10)
    failed = item.begin_attempt(None, MON_10)

    assert (started.attempts, started.download_id, started.last_triggered_at) == (1, "d1", MON_10)
    assert (failed.attempts, failed.download_id, failed.last_triggered_at) == (1, None, None)


def test_attempts_exhausted_at_max_attempts():
    item = _at_time(max_attempts=2)
    assert not item.begin_attempt(None, MON_10).attempts_exhausted()
    assert item.begin_attempt(None, MON_10).begin_attempt(None, MON_10).attempts_exhausted()


def test_one_shot_finish_turns_itself_off_and_keeps_the_outcome():
    item = _at_time().with_first_due(MON_10).begin_attempt("d1", MON_10)

    done = item.finish(ScheduleOutcome.COMPLETED, MON_10 + timedelta(hours=1))

    assert done.is_active is False
    assert done.last_outcome is ScheduleOutcome.COMPLETED
    assert (done.download_id, done.attempts, done.next_due_at) == (None, 0, None)


def test_on_next_live_is_one_shot():
    item = ScheduledDownload(channel_ref=CHANNEL, trigger=ScheduleTrigger.ON_NEXT_LIVE)
    assert item.finish(ScheduleOutcome.COMPLETED, MON_10).is_active is False


def test_recurring_finish_stays_armed_for_the_next_go_live():
    item = ScheduledDownload(channel_ref=CHANNEL, trigger=ScheduleTrigger.RECURRING)
    item = item.begin_attempt("d1", MON_10)

    done = item.finish(ScheduleOutcome.COMPLETED, MON_10)

    assert done.is_active is True and done.attempts == 0 and done.download_id is None


def test_repeating_at_time_advances_to_the_next_occurrence():
    item = (
        _at_time(weekdays=(0, 2))
        .with_first_due(MON_10 - timedelta(days=1))
        .begin_attempt("d", MON_10)
    )

    done = item.finish(ScheduleOutcome.COMPLETED, MON_10 + timedelta(hours=2))

    assert done.is_active is True
    assert done.next_due_at == datetime(2026, 9, 23, 10, 0)  # Wednesday


def test_repeating_at_time_after_a_long_absence_lands_on_the_first_occurrence_still_open():
    """Closed for ten days: the next occurrence is the first one whose
    window is still open — today's, if it is — not the first one after the
    *old* due date (which would replay ten days of missed occurrences)."""
    item = _at_time(weekdays=(0, 1, 2, 3, 4, 5, 6), window_seconds=3600).with_first_due(
        MON_10 - timedelta(days=1)
    )
    ten_days_later = MON_10 + timedelta(days=10, minutes=30)  # 30 min into that day's window

    inside_window = item.finish(ScheduleOutcome.MISSED, ten_days_later)
    after_window = item.finish(ScheduleOutcome.MISSED, ten_days_later + timedelta(hours=1))

    assert inside_window.next_due_at == MON_10 + timedelta(days=10)  # today's, armed at once
    assert after_window.next_due_at == MON_10 + timedelta(days=11)  # today's is over: tomorrow's


# --- rules ------------------------------------------------------------------


def test_rules_are_derived_from_the_favorite_and_independent_of_each_other():
    favorite = Favorite(
        channel_ref=CHANNEL,
        notify_on_live=True,
        auto_download=False,
        preferred_quality="720p",
        preferred_format="mkv",
        download_directory="D:/rec",
        position=3,
    )

    notification = NotificationRule.from_favorite(favorite)
    auto = AutoDownloadRule.from_favorite(favorite)

    assert notification.enabled is True
    assert auto.enabled is False
    assert (auto.quality, auto.file_format, auto.directory, auto.priority) == (
        "720p",
        "mkv",
        "D:/rec",
        3,
    )


def test_auto_download_rule_defaults_quality_to_best():
    rule = AutoDownloadRule.from_favorite(Favorite(channel_ref=CHANNEL, auto_download=True))
    assert rule.quality == "best" and rule.enabled is True
