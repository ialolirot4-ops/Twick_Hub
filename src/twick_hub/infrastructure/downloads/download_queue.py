"""Priority queue of pending download ids: lowest ``priority`` first, and
FIFO among equal priorities (so with every priority left at the default 0
it behaves exactly like the plain FIFO queue it was before FASE 11). This
queue itself doesn't limit concurrency — ``DownloadCoordinator`` does, by
only running a bounded number of workers pulling from it (Master Plan §19:
"workers limitados").
"""

from __future__ import annotations

import asyncio
import itertools


class DownloadQueue:
    def __init__(self) -> None:
        self._queue: asyncio.PriorityQueue[tuple[int, int, str]] = asyncio.PriorityQueue()
        self._arrival = itertools.count()  # the FIFO tie-break

    async def put(self, download_id: str, priority: int = 0) -> None:
        await self._queue.put((priority, next(self._arrival), download_id))

    async def get(self) -> str:
        return (await self._queue.get())[2]

    def task_done(self) -> None:
        self._queue.task_done()

    async def join(self) -> None:
        """Blocks until every item ``put`` has had ``task_done`` called
        for it — lets tests (and a future graceful-shutdown phase) wait
        for the queue to fully drain."""
        await self._queue.join()

    def qsize(self) -> int:
        return self._queue.qsize()
