from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest

from tests.application.fakes import InMemoryScheduledDownloadRepository
from tests.application.scheduling.env import CHANNEL, NOW, OTHER, Env
from twick_hub.application.scheduling.recording import RecordingUnavailableError
from twick_hub.application.scheduling.retry import RetryPolicy
from twick_hub.application.scheduling.scheduler import ScheduledDownloadScheduler, SchedulerConfig
from twick_hub.domain.collections import ScheduledDownload
from twick_hub.domain.enums import DownloadStatus, ScheduleOutcome, SchedulePhase, ScheduleTrigger

_CONFIG = SchedulerConfig(
    max_sleep_seconds=60.0,
    retry=RetryPolicy(base_delay_seconds=30, factor=2, max_delay_seconds=300),
)


class _World:
    def __init__(self, config: SchedulerConfig = _CONFIG) -> None:
        self.env = Env()
        self.repo = InMemoryScheduledDownloadRepository()
        self.demand_syncs = 0
        self.attempts = 0
        real_start = self.env.recorder.start

        async def counting_start(request):
            self.attempts += 1
            return await real_start(request)

        self.env.recorder.start = counting_start  # type: ignore[method-assign]

        async def on_demand_changed() -> None:
            self.demand_syncs += 1

        self.scheduler = ScheduledDownloadScheduler(
            self.repo,
            self.env.downloads,
            self.env.recorder,
            clock=self.env.clock,
            config=config,
            on_demand_changed=on_demand_changed,
        )
        self.scheduler.attach(self.env.bus)

    @property
    def now(self) -> datetime:
        return self.env.clock.now

    def advance(self, **delta) -> None:
        self.env.clock.now += timedelta(**delta)

    async def add(self, item: ScheduledDownload) -> ScheduledDownload:
        item = item.with_first_due(self.now)
        await self.repo.save(item)
        return item

    async def item(self, item_id: str) -> ScheduledDownload:
        (found,) = [i for i in await self.repo.list_all() if i.id == item_id]
        return found

    async def go_live_event(self, channel=CHANNEL) -> None:
        # tracker.observe_live already publishes ChannelWentOnline onto
        # env.bus (same one the scheduler is attached to) — nothing else
        # to publish here.
        await self.env.go_live(channel)
        await self.scheduler.wait_idle()

    async def finish_recording(self, item_id: str, status: DownloadStatus, error=None) -> None:
        item = await self.item(item_id)
        assert item.download_id is not None
        await self.env.finish(item.download_id, status, error)
        await self.scheduler.wait_idle()


def _on_next_live(**fields) -> ScheduledDownload:
    return ScheduledDownload(channel_ref=CHANNEL, trigger=ScheduleTrigger.ON_NEXT_LIVE, **fields)


def _recurring(**fields) -> ScheduledDownload:
    return ScheduledDownload(channel_ref=CHANNEL, trigger=ScheduleTrigger.RECURRING, **fields)


def _at(run_at: datetime, **fields) -> ScheduledDownload:
    return ScheduledDownload(
        channel_ref=CHANNEL, trigger=ScheduleTrigger.AT_TIME, run_at=run_at, **fields
    )


# --- ON_NEXT_LIVE ------------------------------------------------------------


async def test_on_next_live_waits_then_records_the_next_go_live_once():
    w = _World()
    item = await w.add(_on_next_live(priority=3, quality_preference="720p"))
    await w.scheduler.tick()
    assert w.env.engine.enqueued == []  # armed, channel offline

    await w.go_live_event()

    started = await w.item(item.id)
    assert started.phase(w.now) is SchedulePhase.RUNNING
    assert started.attempts == 1 and started.last_triggered_at == w.now
    assert [job.priority for job in w.env.engine.enqueued] == [3]
    (download,) = await w.env.downloads.list_all()
    assert download.quality_label == "720p60"

    await w.finish_recording(item.id, DownloadStatus.COMPLETED)

    done = await w.item(item.id)
    assert done.is_active is False and done.last_outcome is ScheduleOutcome.COMPLETED


async def test_an_item_armed_while_the_channel_is_already_live_records_at_once():
    w = _World()
    await w.env.go_live()
    item = await w.add(_on_next_live())

    await w.scheduler.tick()

    assert (await w.item(item.id)).phase(w.now) is SchedulePhase.RUNNING


async def test_an_armed_item_is_checked_once_then_waits_for_the_go_live_event_for_free():
    w = _World()
    await w.add(_on_next_live())
    await w.scheduler.tick()
    assert w.attempts == 1  # the one check made when it first became armed

    for _ in range(5):
        w.advance(minutes=1)
        await w.scheduler.tick()

    assert w.attempts == 1  # no repeated attempts while nothing changed: no poll


async def test_recurring_records_every_go_live_and_stays_armed():
    w = _World()
    item = await w.add(_recurring())
    await w.scheduler.tick()

    for stream_number in range(2):
        await w.go_live_event()
        assert (await w.item(item.id)).phase(w.now) is SchedulePhase.RUNNING
        await w.finish_recording(item.id, DownloadStatus.COMPLETED)
        await w.env.go_offline()
        again = await w.item(item.id)
        assert again.is_active and again.last_outcome is ScheduleOutcome.COMPLETED, stream_number

    assert len(w.env.engine.enqueued) == 2


async def test_a_go_live_of_another_channel_does_nothing():
    w = _World()
    item = await w.add(_on_next_live())
    await w.scheduler.tick()

    await w.go_live_event(OTHER)

    assert (await w.item(item.id)).phase(w.now) is SchedulePhase.WAITING_LIVE


async def test_a_disabled_item_is_ignored():
    w = _World()
    await w.add(_on_next_live(is_active=False))
    await w.scheduler.tick()

    await w.go_live_event()

    assert w.env.engine.enqueued == []


# --- AT_TIME -----------------------------------------------------------------


async def test_at_time_sleeps_until_due_and_needs_no_watching_before_then():
    w = _World()
    due = NOW + timedelta(
        seconds=30
    )  # inside max_sleep_seconds so the cap doesn't hide the real wake time
    item = await w.add(_at(due))

    delay = await w.scheduler.tick()

    assert delay == 30.0
    assert (await w.item(item.id)).phase(w.now) is SchedulePhase.SCHEDULED
    assert await w.scheduler.watch_demand() == []


async def test_the_sleep_is_capped_so_a_clock_jump_cannot_strand_the_scheduler():
    w = _World()
    await w.add(_at(NOW + timedelta(hours=5)))

    assert await w.scheduler.tick() == 60.0


async def test_at_time_records_when_due_if_the_channel_is_live():
    w = _World()
    await w.env.go_live()
    item = await w.add(_at(NOW + timedelta(minutes=10)))
    await w.scheduler.tick()
    assert w.env.engine.enqueued == []

    w.advance(minutes=10)
    await w.scheduler.tick()

    assert (await w.item(item.id)).phase(w.now) is SchedulePhase.RUNNING


async def test_at_time_waits_inside_its_window_for_a_late_go_live_and_asks_for_watching():
    w = _World()
    item = await w.add(_at(NOW, window_seconds=3600))
    await w.scheduler.tick()  # due now: armed, offline

    assert await w.scheduler.watch_demand() == [CHANNEL]
    assert w.demand_syncs == 1

    w.advance(minutes=20)
    await w.go_live_event()

    assert (await w.item(item.id)).phase(w.now) is SchedulePhase.RUNNING
    await w.finish_recording(item.id, DownloadStatus.COMPLETED)
    done = await w.item(item.id)
    assert done.is_active is False and done.last_outcome is ScheduleOutcome.COMPLETED
    assert await w.scheduler.watch_demand() == []


async def test_at_time_is_missed_when_the_window_closes_without_a_go_live():
    w = _World()
    item = await w.add(_at(NOW, window_seconds=3600))
    await w.scheduler.tick()

    w.advance(hours=1, seconds=1)
    delay = await w.scheduler.tick()

    missed = await w.item(item.id)
    assert missed.is_active is False and missed.last_outcome is ScheduleOutcome.MISSED
    assert delay is None
    assert await w.scheduler.watch_demand() == []


async def test_a_repeating_at_time_advances_to_the_next_occurrence_when_missed():
    w = _World()
    item = await w.add(_at(NOW, weekdays=(0, 1, 2, 3, 4, 5, 6), window_seconds=3600))
    await w.scheduler.tick()

    w.advance(hours=1, seconds=1)
    await w.scheduler.tick()

    after = await w.item(item.id)
    assert after.is_active is True and after.last_outcome is ScheduleOutcome.MISSED
    assert after.next_due_at == NOW + timedelta(days=1)


# --- retries -----------------------------------------------------------------


async def test_a_failed_recording_is_retried_after_a_backoff_then_gives_up():
    w = _World()
    await w.env.go_live()
    item = await w.add(_on_next_live(max_attempts=2))
    await w.scheduler.tick()  # attempt 1 starts
    await w.finish_recording(item.id, DownloadStatus.FAILED, "network")

    waiting = await w.item(item.id)
    assert waiting.phase(w.now) is SchedulePhase.WAITING_LIVE and waiting.attempts == 1
    delay = await w.scheduler.tick()
    assert delay == 30.0  # backing off; nothing retried yet
    assert len(w.env.engine.enqueued) == 1

    w.advance(seconds=30)
    await w.scheduler.tick()  # attempt 2
    assert len(w.env.engine.enqueued) == 2
    await w.finish_recording(item.id, DownloadStatus.FAILED, "network again")

    failed = await w.item(item.id)
    assert failed.is_active is False and failed.last_outcome is ScheduleOutcome.FAILED


async def test_a_failure_to_even_start_counts_as_an_attempt():
    w = _World()
    await w.env.go_live()
    item = await w.add(_on_next_live(max_attempts=2))

    async def boom(job):
        raise ConnectionError("engine down")

    w.env.engine.enqueue = boom  # type: ignore[method-assign]

    await w.scheduler.tick()
    assert (await w.item(item.id)).attempts == 1
    w.advance(seconds=30)
    await w.scheduler.tick()

    failed = await w.item(item.id)
    assert failed.last_outcome is ScheduleOutcome.FAILED and failed.is_active is False


async def test_an_at_time_window_that_closes_after_a_failed_attempt_reports_failed_not_missed():
    w = _World()
    await w.env.go_live()
    item = await w.add(_at(NOW, window_seconds=600, max_attempts=3))
    await w.scheduler.tick()
    await w.finish_recording(item.id, DownloadStatus.FAILED, "x")

    w.advance(seconds=601)
    await w.scheduler.tick()

    assert (await w.item(item.id)).last_outcome is ScheduleOutcome.FAILED


async def test_a_retry_wakes_a_sleeping_loop():
    w = _World()
    await w.env.go_live()
    await w.add(_on_next_live())
    await w.scheduler.tick()
    w.scheduler._wakeup.clear()

    item = (await w.repo.list_all())[0]
    await w.finish_recording(item.id, DownloadStatus.FAILED, "x")

    assert w.scheduler._wakeup.is_set()  # nothing else would have woken it


async def test_a_cancelled_recording_finishes_the_item_without_retrying():
    w = _World()
    await w.env.go_live()
    item = await w.add(_on_next_live())
    await w.scheduler.tick()

    await w.finish_recording(item.id, DownloadStatus.CANCELLED)

    done = await w.item(item.id)
    assert done.last_outcome is ScheduleOutcome.CANCELLED and done.is_active is False
    assert len(w.env.engine.enqueued) == 1


# --- shared recordings --------------------------------------------------------


async def test_an_item_follows_a_recording_someone_else_already_started():
    w = _World()
    await w.env.go_live()
    from twick_hub.application.scheduling.recording import RecordingRequest

    existing = await w.env.recorder.start(RecordingRequest(CHANNEL))
    item = await w.add(_on_next_live())

    await w.scheduler.tick()

    followed = await w.item(item.id)
    assert followed.download_id == existing.id
    assert len(w.env.engine.enqueued) == 1  # no second recording
    await w.finish_recording(item.id, DownloadStatus.COMPLETED)
    assert (await w.item(item.id)).last_outcome is ScheduleOutcome.COMPLETED


# --- demand -----------------------------------------------------------------


async def test_demand_is_reported_only_when_it_changes():
    w = _World()
    await w.add(_on_next_live())
    await w.scheduler.tick()
    await w.scheduler.tick()
    await w.scheduler.tick()

    assert w.demand_syncs == 1


async def test_demand_lists_each_channel_once():
    w = _World()
    await w.add(_on_next_live())
    await w.add(_recurring())
    assert await w.scheduler.watch_demand() == [CHANNEL]


# --- idle behaviour and restart ------------------------------------------------


async def test_nothing_scheduled_means_no_timer_at_all():
    w = _World()

    assert await w.scheduler.tick() is None


async def test_run_forever_sleeps_until_something_is_created_then_wakes():
    w = _World()
    await w.env.go_live()
    listed = [0]
    real_list = w.repo.list_all

    async def counting_list(**kwargs):
        listed[0] += 1
        return await real_list(**kwargs)

    w.repo.list_all = counting_list  # type: ignore[method-assign]
    task = asyncio.create_task(w.scheduler.run_forever())
    await asyncio.sleep(0.1)
    idle_reads = listed[0]
    await asyncio.sleep(0.2)
    assert listed[0] == idle_reads  # asleep: no reads, no timers

    await w.add(_on_next_live())
    w.scheduler.refresh()
    await asyncio.sleep(0.1)

    assert len(w.env.engine.enqueued) == 1
    await w.scheduler.stop()
    await asyncio.wait_for(task, timeout=1)


async def test_recover_settles_an_item_whose_download_failed_while_the_app_was_closed():
    w = _World()
    await w.env.go_live()
    item = await w.add(_on_next_live(max_attempts=5))
    await w.scheduler.tick()  # starts recording, attempts=1
    running = await w.item(item.id)
    assert running.download_id is not None and running.attempts == 1

    # The app "closes" while DOWNLOADING; a fresh scheduler starts and the
    # download engine reports (via RecoverInterruptedDownloadsUseCase,
    # simulated here by just setting the status) that it never finished.
    from dataclasses import replace

    stored = await w.env.downloads.get(running.download_id)
    assert stored is not None
    await w.env.downloads.save(
        replace(
            stored,
            status=DownloadStatus.FAILED,
            error_message="interrupted by application shutdown",
        )
    )
    fresh = ScheduledDownloadScheduler(
        w.repo, w.env.downloads, w.env.recorder, clock=w.env.clock, config=_CONFIG
    )

    await fresh.recover()

    after = await w.item(item.id)
    assert after.download_id is None and after.is_active is True
    assert after.phase(w.now) is SchedulePhase.WAITING_LIVE  # ready to try again


async def test_recover_treats_a_missing_download_record_as_a_failed_attempt():
    w = _World()
    await w.env.go_live()
    item = await w.add(_on_next_live(max_attempts=1))
    await w.scheduler.tick()
    running = await w.item(item.id)
    from dataclasses import replace

    await w.repo.save(replace(running, download_id="vanished"))  # the row itself is gone
    fresh = ScheduledDownloadScheduler(
        w.repo, w.env.downloads, w.env.recorder, clock=w.env.clock, config=_CONFIG
    )

    await fresh.recover()

    after = await w.item(item.id)
    assert after.download_id is None
    # max_attempts=1: exhausted
    assert after.is_active is False and after.last_outcome is ScheduleOutcome.FAILED


async def test_recover_leaves_a_still_running_download_alone():
    w = _World()
    await w.env.go_live()
    item = await w.add(_on_next_live())
    await w.scheduler.tick()
    running = await w.item(item.id)
    fresh = ScheduledDownloadScheduler(
        w.repo, w.env.downloads, w.env.recorder, clock=w.env.clock, config=_CONFIG
    )

    await fresh.recover()  # the download is still QUEUED: nothing to settle

    after = await w.item(item.id)
    assert after.download_id == running.download_id and after.attempts == 1


# FASE 18 — Testing: everything below closes gaps found by measuring
# coverage against the real suite (docs/phase-state.md) — a handful of
# branches every existing scenario above happened to route around.


async def test_recover_skips_an_item_that_never_attempted_a_recording():
    """``recover()``'s very first check — ``download_id is None`` — is
    distinct from every recover() scenario above, which all first call
    ``tick()`` to get a real ``download_id`` going before recovering. An
    item that was created but never got as far as a first attempt (the
    channel simply hasn't gone live yet) has nothing for recover() to
    settle at all."""
    w = _World()
    item = await w.add(_on_next_live())  # never ticked, never went live

    await w.scheduler.recover()  # must not touch this item

    after = await w.item(item.id)
    assert after.download_id is None
    assert after.is_active is True


async def test_recording_unavailable_finishes_the_item_as_failed_without_retrying():
    """Unlike a transient failure (ConnectionError, etc. — see
    test_a_failure_to_even_start_counts_as_an_attempt above), an adapter
    reporting the recording itself as impossible (no download provider for
    this platform/media kind) can never be fixed by retrying, so it must
    finish the item immediately rather than counting it as a normal
    failed attempt."""
    w = _World()
    await w.env.go_live()
    item = await w.add(_on_next_live(max_attempts=3))

    async def unavailable(request):
        raise RecordingUnavailableError("no download provider for this platform")

    w.env.recorder.start = unavailable  # type: ignore[method-assign]

    await w.scheduler.tick()

    failed = await w.item(item.id)
    assert failed.is_active is False
    assert failed.last_outcome is ScheduleOutcome.FAILED
    assert failed.attempts == 0  # never counted as a retryable attempt


async def test_a_cancelled_error_starting_a_recording_propagates_instead_of_being_swallowed():
    """``asyncio.CancelledError`` means the app itself is shutting down —
    it must propagate out of the scheduler, not be treated as just another
    failed recording attempt the way a generic ``Exception`` is."""
    w = _World()
    await w.env.go_live()
    await w.add(_on_next_live())

    async def cancelled(request):
        raise asyncio.CancelledError()

    w.env.recorder.start = cancelled  # type: ignore[method-assign]

    with pytest.raises(asyncio.CancelledError):
        await w.scheduler.tick()


async def test_a_failing_demand_callback_is_logged_not_raised():
    """``on_demand_changed`` is caller-supplied (wires up the live monitor
    in the real app) — if it raises, ``_sync_demand`` must log and move
    on, not let the failure escape out of an ordinary tick()."""
    w = _World()

    async def raising_callback() -> None:
        raise RuntimeError("live monitor is not ready yet")

    w.scheduler._on_demand_changed = raising_callback  # type: ignore[attr-defined]
    await w.add(_on_next_live())  # the first-ever watched item: demand changes from empty

    await w.scheduler.tick()  # must not raise


async def test_wait_returns_on_a_genuine_timeout_without_the_wakeup_having_fired():
    """Distinct from every other test above, which only ever exercises
    ``_wait`` through scenarios where the wakeup event fires (or delay is
    ``None``, waiting forever) — a real, unfired timeout is its own branch."""
    w = _World()

    await w.scheduler._wait(0.01)  # nothing ever sets self._wakeup

    assert w.scheduler._wakeup.is_set() is False
