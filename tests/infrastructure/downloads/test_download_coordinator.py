from __future__ import annotations

import asyncio

import pytest

from twick_hub.infrastructure.downloads.download_coordinator import DownloadCoordinator, Executor
from twick_hub.infrastructure.downloads.download_queue import DownloadQueue


class FakeExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool, bool]] = []
        self._raise_for: set[str] = set()

    def raise_for(self, download_id: str) -> None:
        self._raise_for.add(download_id)

    async def run(self, download_id: str, *, is_cancelled, is_paused) -> None:
        self.calls.append((download_id, is_cancelled(), is_paused()))
        if download_id in self._raise_for:
            raise RuntimeError("boom")


def _coordinator(
    queue: DownloadQueue,
    executor: Executor,
    *,
    worker_count: int = 1,
    cancelled: set[str] | None = None,
    paused: set[str] | None = None,
) -> DownloadCoordinator:
    cancelled = cancelled if cancelled is not None else set()
    paused = paused if paused is not None else set()
    return DownloadCoordinator(
        queue,
        executor,
        worker_count=worker_count,
        is_cancelled=lambda d: d in cancelled,
        is_paused=lambda d: d in paused,
    )


async def test_worker_processes_enqueued_jobs():
    queue = DownloadQueue()
    executor = FakeExecutor()
    coordinator = _coordinator(queue, executor)

    coordinator.start()
    await queue.put("job-1")
    await queue.put("job-2")
    await queue.join()
    await coordinator.stop()

    assert [call[0] for call in executor.calls] == ["job-1", "job-2"]


async def test_is_cancelled_and_is_paused_are_bound_per_download_id():
    queue = DownloadQueue()
    executor = FakeExecutor()
    coordinator = _coordinator(queue, executor, cancelled={"job-2"}, paused={"job-1"})

    coordinator.start()
    await queue.put("job-1")
    await queue.put("job-2")
    await queue.join()
    await coordinator.stop()

    calls = dict(
        (download_id, (cancelled, paused)) for download_id, cancelled, paused in executor.calls
    )
    assert calls["job-1"] == (False, True)
    assert calls["job-2"] == (True, False)


async def test_one_bad_job_does_not_kill_the_worker():
    queue = DownloadQueue()
    executor = FakeExecutor()
    executor.raise_for("bad-job")
    coordinator = _coordinator(queue, executor)

    coordinator.start()
    await queue.put("bad-job")
    await queue.put("good-job")
    await queue.join()
    await coordinator.stop()

    assert [call[0] for call in executor.calls] == ["bad-job", "good-job"]


async def test_concurrency_is_bounded_by_worker_count():
    queue = DownloadQueue()
    in_flight = 0
    max_seen = 0

    class TrackingExecutor:
        async def run(self, download_id: str, *, is_cancelled, is_paused) -> None:
            nonlocal in_flight, max_seen
            in_flight += 1
            max_seen = max(max_seen, in_flight)
            await asyncio.sleep(0.01)
            in_flight -= 1

    coordinator = _coordinator(queue, TrackingExecutor(), worker_count=2)
    coordinator.start()
    for i in range(6):
        await queue.put(f"job-{i}")
    await queue.join()
    await coordinator.stop()

    assert max_seen <= 2


async def test_stop_is_graceful_and_idempotent():
    queue = DownloadQueue()
    coordinator = _coordinator(queue, FakeExecutor())
    coordinator.start()
    await coordinator.stop()
    await coordinator.stop()  # must not raise


async def test_worker_count_below_one_rejected():
    with pytest.raises(ValueError):
        _coordinator(DownloadQueue(), FakeExecutor(), worker_count=0)
