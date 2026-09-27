"""AutoDownloadRule in action: record a favorite every time it goes live.

Event-driven — there is no loop and no timer here. It costs nothing while
nobody is live, and reacts to ``ChannelWentOnline`` (including the
``initial=True`` kind, so a stream already in progress when the app starts
is caught too). Failures are retried with backoff up to a limit; a stream
that ends resets the count.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any

from twick_hub.application.scheduling.recording import (
    AlreadyRecordingError,
    ChannelNotLiveError,
    RecordingRequest,
    RecordingService,
    RecordingUnavailableError,
)
from twick_hub.application.scheduling.retry import RetryPolicy
from twick_hub.domain.enums import DownloadStatus
from twick_hub.domain.events import (
    ChannelWentOffline,
    ChannelWentOnline,
    DomainEvent,
    DownloadFinished,
    EventBus,
)
from twick_hub.domain.protocols import FavoriteRepository
from twick_hub.domain.scheduling import AutoDownloadRule
from twick_hub.domain.value_objects import PlatformRef

logger = logging.getLogger(__name__)


class AutoDownloadService:
    def __init__(
        self,
        favorites: FavoriteRepository,
        recorder: RecordingService,
        *,
        retry: RetryPolicy | None = None,
        max_attempts: int = 3,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._favorites = favorites
        self._recorder = recorder
        self._retry = retry or RetryPolicy()
        self._max_attempts = max_attempts
        self._sleep = sleep
        self._owned: dict[str, PlatformRef] = {}  # download id → channel
        self._failures: dict[PlatformRef, int] = {}
        self._retry_tasks: dict[PlatformRef, asyncio.Task[None]] = {}
        self._tasks: set[asyncio.Task[Any]] = set()

    def attach(self, bus: EventBus) -> None:
        bus.subscribe(self._on_event)

    def _on_event(self, event: DomainEvent) -> None:
        # Never do the work inline: the bus is awaited by the live monitor,
        # and starting a recording is several network round trips.
        self._spawn(self.handle_event(event))

    def _spawn(self, coro: Coroutine[Any, Any, None]) -> None:
        task = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def wait_idle(self) -> None:
        """Waits for handlers already spawned (not for pending retry timers)."""
        while pending := [task for task in self._tasks if not task.done()]:
            await asyncio.gather(*pending, return_exceptions=True)

    async def stop(self) -> None:
        for task in [*self._retry_tasks.values(), *self._tasks]:
            task.cancel()
        await asyncio.gather(*self._retry_tasks.values(), *self._tasks, return_exceptions=True)
        self._retry_tasks.clear()

    async def handle_event(self, event: DomainEvent) -> None:
        if isinstance(event, ChannelWentOnline):
            await self._record(event.channel_ref)
        elif isinstance(event, ChannelWentOffline):
            self._failures.pop(event.channel_ref, None)
            self._cancel_retry(event.channel_ref)
        elif isinstance(event, DownloadFinished):
            channel_ref = self._owned.pop(event.download_id, None)
            if channel_ref is None:
                return  # someone else's download
            if event.status is DownloadStatus.FAILED:
                self._on_failure(channel_ref, event.error_message)
            else:
                self._failures.pop(channel_ref, None)

    # --- internals ------------------------------------------------------

    async def _record(self, channel_ref: PlatformRef) -> None:
        favorite = await self._favorites.get_by_channel(channel_ref)
        if favorite is None:
            return
        rule = AutoDownloadRule.from_favorite(favorite)
        if not rule.enabled or channel_ref in self._retry_tasks:
            return
        try:
            download = await self._recorder.start(
                RecordingRequest(
                    channel_ref=channel_ref,
                    quality=rule.quality,
                    file_format=rule.file_format,
                    directory=rule.directory,
                    priority=rule.priority,
                )
            )
        except (AlreadyRecordingError, ChannelNotLiveError):
            return  # already covered, or nothing to record
        except RecordingUnavailableError as exc:
            logger.warning("auto-download of %s is not possible: %s", channel_ref, exc)
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._on_failure(channel_ref, str(exc))
            return
        self._owned[download.id] = channel_ref

    def _on_failure(self, channel_ref: PlatformRef, reason: str | None) -> None:
        failures = self._failures.get(channel_ref, 0) + 1
        self._failures[channel_ref] = failures
        if failures >= self._max_attempts:
            logger.warning(
                "auto-download of %s gave up after %d attempts: %s", channel_ref, failures, reason
            )
            return
        delay = self._retry.delay_for(failures)
        logger.warning(
            "auto-download of %s failed (%s); retrying in %.0fs", channel_ref, reason, delay
        )
        self._cancel_retry(channel_ref)
        self._retry_tasks[channel_ref] = asyncio.get_running_loop().create_task(
            self._retry_later(channel_ref, delay)
        )

    async def _retry_later(self, channel_ref: PlatformRef, delay: float) -> None:
        try:
            await self._sleep(delay)
        finally:
            self._retry_tasks.pop(channel_ref, None)
        await self._record(channel_ref)

    def _cancel_retry(self, channel_ref: PlatformRef) -> None:
        task = self._retry_tasks.pop(channel_ref, None)
        if task is not None:
            task.cancel()
