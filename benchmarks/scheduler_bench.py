"""Reproducible, SYNTHETIC measurements for the FASE 11 scheduler.

    python benchmarks/scheduler_bench.py

What this measures: how many wake-ups ``ScheduledDownloadScheduler.tick()``
needs over a simulated day for a given number of AT_TIME items, compared
with the naive alternative of polling every item every N seconds. No real
network, no real clock — a virtual clock is stepped by exactly the delay
``tick()`` itself returns, which is the point: the scheduler never wakes up
for no reason.
"""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta

from tests.application.fakes import InMemoryScheduledDownloadRepository
from tests.application.scheduling.env import Env
from twick_hub.application.scheduling.scheduler import ScheduledDownloadScheduler, SchedulerConfig
from twick_hub.domain.collections import ScheduledDownload
from twick_hub.domain.enums import Platform, ScheduleTrigger
from twick_hub.domain.value_objects import PlatformRef

DAY = timedelta(days=1)


async def wakeups_over_a_day(item_count: int, spread_hours: int = 20) -> int:
    env = Env()
    repo = InMemoryScheduledDownloadRepository()
    scheduler = ScheduledDownloadScheduler(
        repo, env.downloads, env.recorder, clock=env.clock,
        config=SchedulerConfig(max_sleep_seconds=3600),  # generous cap: isolate the real math
    )  # fmt: skip

    start = env.clock.now
    for i in range(item_count):
        # Spread across the day so items rarely coincide, and never let the
        # channel be live (each stays SCHEDULED -> WAITING_LIVE -> EXPIRED
        # without a recording, so only the timing loop is measured).
        run_at = start + timedelta(hours=(i * spread_hours / item_count) % spread_hours, minutes=1)
        item = ScheduledDownload(
            channel_ref=PlatformRef(platform=Platform.TWITCH, external_id=f"c{i}"),
            trigger=ScheduleTrigger.AT_TIME,
            run_at=run_at,
            window_seconds=120,
        ).with_first_due(start)
        await repo.save(item)

    wakeups = 0
    deadline = start + DAY
    while env.clock.now < deadline:
        delay = await scheduler.tick()
        wakeups += 1
        if delay is None:
            break
        env.clock.now += timedelta(seconds=delay)
    return wakeups


def naive_polls_over_a_day(poll_interval_seconds: float) -> int:
    return int(DAY.total_seconds() // poll_interval_seconds)


def main() -> None:
    print("== scheduler wake-ups over one simulated day (AT_TIME items, no live channel) ==")
    for count in (1, 20, 200):
        wakeups = asyncio.run(wakeups_over_a_day(count))
        print(json.dumps({"items": count, "wakeups": wakeups}))

    print("\n== compared with polling every item every N seconds, 20 items, one day ==")
    for interval in (10, 60):
        naive = 20 * naive_polls_over_a_day(interval)
        print(f"poll every {interval:>3d}s per item: {naive:>7d} checks/day")
    real = asyncio.run(wakeups_over_a_day(20))
    print(f"{'ScheduledDownloadScheduler':>24s}: {real:>7d} wake-ups/day")


if __name__ == "__main__":
    main()
