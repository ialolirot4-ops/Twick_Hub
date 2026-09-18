from __future__ import annotations

from twick_hub.infrastructure.downloads.download_queue import DownloadQueue


async def test_put_and_get_preserve_fifo_order():
    queue = DownloadQueue()
    await queue.put("a")
    await queue.put("b")

    assert await queue.get() == "a"
    assert await queue.get() == "b"


async def test_qsize_reflects_pending_items():
    queue = DownloadQueue()
    assert queue.qsize() == 0

    await queue.put("a")
    assert queue.qsize() == 1

    await queue.get()
    assert queue.qsize() == 0


async def test_task_done_does_not_raise_after_a_get():
    queue = DownloadQueue()
    await queue.put("a")
    await queue.get()
    queue.task_done()  # would raise ValueError if called more times than get()
