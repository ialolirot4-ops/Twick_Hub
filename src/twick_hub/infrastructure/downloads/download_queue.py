"""FIFO queue of pending download ids. This queue itself doesn't limit
concurrency — ``DownloadCoordinator`` does, by only running a bounded
number of workers pulling from it (Master Plan §19: "workers limitados").
"""

from __future__ import annotations

import asyncio


class DownloadQueue:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue()

    async def put(self, download_id: str) -> None:
        await self._queue.put(download_id)

    async def get(self) -> str:
        return await self._queue.get()

    def task_done(self) -> None:
        self._queue.task_done()

    async def join(self) -> None:
        """Blocks until every item ``put`` has had ``task_done`` called
        for it — lets tests (and a future graceful-shutdown phase) wait
        for the queue to fully drain."""
        await self._queue.join()

    def qsize(self) -> int:
        return self._queue.qsize()
