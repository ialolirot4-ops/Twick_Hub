"""Pure wall-clock arithmetic for scheduled downloads.

Naive local datetimes throughout, like the rest of the domain
(``datetime.now`` defaults everywhere): "every day at 20:00" means 20:00 on
the user's own clock, which is what a person scheduling a recording
expects across a DST change too. The only cost is the hour that doesn't
exist (or exists twice) on the transition night — accepted, and the
scheduler re-reads the clock at least once a minute so a jump never
strands it (application/scheduling/scheduler.py).
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

ALL_WEEKDAYS = tuple(range(7))  # 0 = Monday, like datetime.weekday()


def next_occurrence(at: time, weekdays: tuple[int, ...], after: datetime) -> datetime:
    """The first moment strictly after ``after`` that falls at ``at`` on an
    allowed weekday (an empty ``weekdays`` allows every day)."""
    allowed = set(weekdays) or set(ALL_WEEKDAYS)
    day = after.date()
    for offset in range(8):  # a week always contains an allowed day
        candidate = datetime.combine(day + timedelta(days=offset), at)
        if candidate.weekday() in allowed and candidate > after:
            return candidate
    raise ValueError("weekdays must be within 0..6")
