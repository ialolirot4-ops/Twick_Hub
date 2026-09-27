"""ScheduledDownload in action (Master Plan §20 / FASE 11).

Three things can start a scheduled recording, and none of them is a poll:

* **A go-live event** (``ChannelWentOnline``) for a channel that has an armed
  item — free, the live monitor already produces it.
* **A due time** (``AT_TIME``): the scheduler sleeps until exactly the next
  moment anything needs attention (an item coming due, a window closing, a
  retry) and wakes then. With nothing scheduled it has *no timer at all* and
  waits on an event until an item is created (``refresh``). While items exist
  it still re-reads the clock at least every ``max_sleep_seconds``, so a
  suspend/resume or a clock change can delay a start by at most that long.
* **Arming** an item — a single "is it live right now?" check when it first
  becomes armed (after creation, at its due time, or after a restart), which
  is what catches a stream that was already live.

An armed item that isn't live yet keeps waiting — for the whole
``window_seconds`` for ``AT_TIME``, indefinitely for the event-based
triggers. Which channels the live monitor must watch on the scheduler's
behalf is ``watch_demand()``; ``on_demand_changed`` lets the monitor's
``sync()`` be called when that changes.

State lives in the repository (``next_due_at``, ``attempts``, ``download_id``,
``last_outcome``), never only in memory, so a restart resumes where the app
stopped: an occurrence whose window has closed is recorded as MISSED, one
still inside its window is armed at once, and an item whose recording was
interrupted is reconciled against what the download actually ended as.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any

from twick_hub.application.scheduling.recording import (
    AlreadyRecordingError,
    ChannelNotLiveError,
    RecordingRequest,
    RecordingService,
    RecordingUnavailableError,
)
from twick_hub.application.scheduling.retry import RetryPolicy
from twick_hub.domain.collections import ScheduledDownload
from twick_hub.domain.enums import DownloadStatus, ScheduleOutcome, SchedulePhase, ScheduleTrigger
from twick_hub.domain.events import (
    ChannelWentOnline,
    DomainEvent,
    DownloadFinished,
    EventBus,
)
from twick_hub.domain.protocols import DownloadRepository, ScheduledDownloadRepository
from twick_hub.domain.value_objects import PlatformRef

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SchedulerConfig:
    max_sleep_seconds: float = 60.0
    retry: RetryPolicy = field(default_factory=RetryPolicy)


class ScheduledDownloadScheduler:
    def __init__(
        self,
        repository: ScheduledDownloadRepository,
        downloads: DownloadRepository,
        recorder: RecordingService,
        *,
        clock: Callable[[], datetime] = datetime.now,
        config: SchedulerConfig | None = None,
        on_demand_changed: Callable[[], Awaitable[object]] | None = None,
    ) -> None:
        self._repo = repository
        self._downloads = downloads
        self._recorder = recorder
        self._clock = clock
        self._config = config or SchedulerConfig()
        self._on_demand_changed = on_demand_changed

        self._lock = asyncio.Lock()  # one state change at a time: events, ticks and recovery
        self._wakeup = asyncio.Event()
        self._stopped = False
        self._armed: set[str] = set()  # items already checked once since they became armed
        self._retry_at: dict[str, datetime] = {}
        self._last_demand: frozenset[PlatformRef] | None = None
        self._tasks: set[asyncio.Task[Any]] = set()

    # --- wiring ----------------------------------------------------------

    def attach(self, bus: EventBus) -> None:
        bus.subscribe(self._on_event)

    def _on_event(self, event: DomainEvent) -> None:
        # Not inline: the bus is awaited by whoever published, and starting a
        # recording takes several network round trips.
        task = asyncio.get_running_loop().create_task(self.handle_event(event))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def wait_idle(self) -> None:
        while pending := [task for task in self._tasks if not task.done()]:
            await asyncio.gather(*pending, return_exceptions=True)

    def refresh(self) -> None:
        """An item was created, edited or deleted: re-evaluate now."""
        self._wakeup.set()

    async def watch_demand(self) -> list[PlatformRef]:
        """Channels the live monitor must watch for the scheduler: every
        armed item that isn't recording yet."""
        now = self._clock()
        channels: dict[PlatformRef, None] = {}
        for item in await self._repo.list_all():
            if item.phase(now) is SchedulePhase.WAITING_LIVE:
                channels[item.channel_ref] = None
        return list(channels)

    # --- events ----------------------------------------------------------

    async def handle_event(self, event: DomainEvent) -> None:
        async with self._lock:
            now = self._clock()
            if isinstance(event, ChannelWentOnline):
                for item in await self._repo.list_all():
                    if item.channel_ref == event.channel_ref and (
                        item.phase(now) is SchedulePhase.WAITING_LIVE
                    ):
                        await self._try_start(item, now)
            elif isinstance(event, DownloadFinished):
                for item in await self._repo.list_all():
                    if item.download_id == event.download_id:
                        await self._on_download_finished(
                            item, event.status, event.error_message, now
                        )
            await self._sync_demand()

    # --- the loop --------------------------------------------------------

    async def run_forever(self) -> None:
        await self.recover()
        while not self._stopped:
            delay = await self.tick()
            await self._wait(delay)

    async def stop(self) -> None:
        self._stopped = True
        self._wakeup.set()

    async def recover(self) -> None:
        """Restart recovery for items that were recording when the app last
        stopped: each is settled against what its download ended as. (Run
        ``RecoverInterruptedDownloadsUseCase`` first, so an interrupted live
        capture already reads FAILED rather than still DOWNLOADING.)"""
        async with self._lock:
            now = self._clock()
            for item in await self._repo.list_all():
                if item.download_id is None:
                    continue
                download = await self._downloads.get(item.download_id)
                if download is None:
                    await self._on_download_finished(
                        item, DownloadStatus.FAILED, "download record missing", now
                    )
                elif download.status in _TERMINAL:
                    await self._on_download_finished(
                        item, download.status, download.error_message, now
                    )
                # else: still queued/running in this process — its own
                # DownloadFinished will settle it
            await self._sync_demand()

    async def tick(self) -> float | None:
        """Does everything that is due right now and returns how many
        seconds until something next needs attention (``None``: nothing
        ever will, until ``refresh``)."""
        async with self._lock:
            now = self._clock()
            wake_at: list[datetime] = []
            still_armed: set[str] = set()

            for item in await self._repo.list_all():
                phase = item.phase(now)
                if phase is SchedulePhase.EXPIRED:
                    outcome = ScheduleOutcome.FAILED if item.attempts else ScheduleOutcome.MISSED
                    logger.info("scheduled download %s: window closed (%s)", item.id, outcome.value)
                    await self._save(item.finish(outcome, now))
                    self._retry_at.pop(item.id, None)
                    continue
                if phase is SchedulePhase.SCHEDULED and item.next_due_at is not None:
                    wake_at.append(item.next_due_at)
                if phase is SchedulePhase.WAITING_LIVE:
                    still_armed.add(item.id)
                    retry_at = self._retry_at.get(item.id)
                    if retry_at is not None and retry_at > now:
                        wake_at.append(retry_at)  # backing off after a failed attempt
                    elif retry_at is not None or item.id not in self._armed:
                        # a retry that is due, or the one check made when an
                        # item first becomes armed (catches a stream that is
                        # already live) — never a periodic poll
                        self._retry_at.pop(item.id, None)
                        await self._try_start(item, now)
                        pending = self._retry_at.get(item.id)
                        if pending is not None:
                            wake_at.append(pending)
                    if item.trigger is ScheduleTrigger.AT_TIME and item.next_due_at is not None:
                        wake_at.append(item.next_due_at + item.window)

            self._armed = still_armed
            await self._sync_demand()

            if not wake_at:
                return None
            seconds = max(0.0, (min(wake_at) - now).total_seconds())
            return min(seconds, self._config.max_sleep_seconds)

    # --- attempts and outcomes --------------------------------------------

    async def _try_start(self, item: ScheduledDownload, now: datetime) -> None:
        self._armed.add(item.id)
        request = RecordingRequest(
            channel_ref=item.channel_ref,
            quality=item.quality_preference,
            file_format=item.preferred_format,
            directory=item.download_directory,
            priority=item.priority,
        )
        try:
            download = await self._recorder.start(request)
        except ChannelNotLiveError:
            return  # stay armed; the go-live event (or the next window check) will come
        except AlreadyRecordingError as exc:
            # e.g. an auto-download rule is already recording this channel:
            # follow that recording instead of starting a second one.
            await self._save(replace(item, download_id=exc.download_id, last_triggered_at=now))
            return
        except RecordingUnavailableError as exc:
            logger.warning("scheduled download %s cannot record: %s", item.id, exc)
            await self._save(item.finish(ScheduleOutcome.FAILED, now))
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("scheduled download %s: attempt failed: %s", item.id, exc)
            await self._after_failed_attempt(item.begin_attempt(None, now), now)
            return
        await self._save(item.begin_attempt(download.id, now))

    async def _on_download_finished(
        self, item: ScheduledDownload, status: DownloadStatus, error: str | None, now: datetime
    ) -> None:
        if status is DownloadStatus.COMPLETED:
            await self._save(item.finish(ScheduleOutcome.COMPLETED, now))
        elif status is DownloadStatus.CANCELLED:
            await self._save(item.finish(ScheduleOutcome.CANCELLED, now))
        else:
            logger.warning("scheduled download %s: recording failed: %s", item.id, error)
            await self._after_failed_attempt(replace(item, download_id=None), now)

    async def _after_failed_attempt(self, item: ScheduledDownload, now: datetime) -> None:
        if item.attempts_exhausted():
            await self._save(item.finish(ScheduleOutcome.FAILED, now))
            self._retry_at.pop(item.id, None)
            return
        self._retry_at[item.id] = now + timedelta(
            seconds=self._config.retry.delay_for(item.attempts)
        )
        await self._save(item)
        self._wakeup.set()  # the loop may be asleep with nothing else to wait for

    # --- internals ---------------------------------------------------------

    async def _save(self, item: ScheduledDownload) -> None:
        await self._repo.save(item)

    async def _sync_demand(self) -> None:
        demand = frozenset(await self.watch_demand())
        if demand == self._last_demand:
            return
        self._last_demand = demand
        if self._on_demand_changed is not None:
            try:
                await self._on_demand_changed()
            except Exception:
                logger.exception("could not update the live-monitor demand")

    async def _wait(self, delay: float | None) -> None:
        try:
            await asyncio.wait_for(self._wakeup.wait(), timeout=delay)
        except TimeoutError:
            return
        self._wakeup.clear()


_TERMINAL = frozenset({DownloadStatus.COMPLETED, DownloadStatus.FAILED, DownloadStatus.CANCELLED})
