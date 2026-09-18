"""Owns a bounded pool of worker tasks (Master Plan §19: "workers
limitados", never a thread — or task — per segment; here it's a task per
*worker*, not per job or per segment) pulling download ids off
``DownloadQueue`` and driving each through ``DownloadExecutor``.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from typing import Protocol, runtime_checkable

from twick_hub.infrastructure.downloads.download_queue import DownloadQueue


@runtime_checkable
class Executor(Protocol):
    """What ``DownloadCoordinator`` needs from ``DownloadExecutor`` — a
    Protocol, matching the same testability pattern as ``HlsReader``
    (download_executor.py) and ``Coordinator`` (download_service.py)."""

    async def run(
        self, download_id: str, *, is_cancelled: Callable[[], bool], is_paused: Callable[[], bool]
    ) -> None: ...


class DownloadCoordinator:
    def __init__(
        self,
        queue: DownloadQueue,
        executor: Executor,
        *,
        worker_count: int = 3,
        is_cancelled: Callable[[str], bool],
        is_paused: Callable[[str], bool],
    ) -> None:
        if worker_count < 1:
            raise ValueError("worker_count must be at least 1")
        self._queue = queue
        self._executor = executor
        self._worker_count = worker_count
        self._is_cancelled = is_cancelled
        self._is_paused = is_paused
        self._workers: list[asyncio.Task[None]] = []

    def start(self) -> None:
        if self._workers:
            return  # already running
        self._workers = [
            asyncio.create_task(self._worker_loop()) for _ in range(self._worker_count)
        ]

    async def stop(self) -> None:
        for worker in self._workers:
            worker.cancel()
        for worker in self._workers:
            with contextlib.suppress(asyncio.CancelledError):
                await worker
        self._workers = []

    async def _worker_loop(self) -> None:
        while True:
            download_id = await self._queue.get()
            try:
                await self._executor.run(
                    download_id,
                    is_cancelled=lambda d=download_id: self._is_cancelled(d),
                    is_paused=lambda d=download_id: self._is_paused(d),
                )
            except Exception:  # noqa: BLE001 - one bad job must not kill this worker permanently
                pass
            finally:
                self._queue.task_done()
