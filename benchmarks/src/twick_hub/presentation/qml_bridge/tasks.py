"""Schedules coroutines from QML-facing slots without blocking Qt.

The QML bridges (``*_model.py``) are synchronous Qt objects that need to
call async use cases. ``TaskRunner`` is the one place that turns "run this
coroutine" into a task on the app's (qasync) event loop, keeps a strong
reference until it finishes (asyncio only holds weak ones) and logs any
exception instead of letting it vanish. The scheduling function is
injected — ``Application`` passes ``loop.create_task``; tests pass
whatever they need — so nothing here reaches for a global loop.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

logger = logging.getLogger(__name__)

Spawn = Callable[[Coroutine[Any, Any, Any]], "asyncio.Future[Any] | asyncio.Task[Any] | None"]


class TaskRunner:
    def __init__(self, spawn: Spawn) -> None:
        self._spawn = spawn
        self._pending: set[asyncio.Future[Any]] = set()

    def run(self, coro: Coroutine[Any, Any, Any]) -> None:
        task = self._spawn(coro)
        if task is None:  # a test spawner that consumed the coroutine itself
            return
        self._pending.add(task)
        task.add_done_callback(self._finished)

    def _finished(self, task: asyncio.Future[Any]) -> None:
        self._pending.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            logger.error("Background UI task failed", exc_info=error)
