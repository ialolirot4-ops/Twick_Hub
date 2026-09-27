from __future__ import annotations

import asyncio

import pytest

from twick_hub.application.live_monitor.polling_policy import AdaptiveInterval, PollingConfig
from twick_hub.application.live_monitor.supervision import supervise

_INSTANT = AdaptiveInterval(
    PollingConfig(
        base_interval=0.001, max_quiet_interval=0.001, max_backoff_interval=0.005, jitter_ratio=0.0
    )
)


async def test_restarts_a_crashing_loop_and_reports_each_crash():
    stop = asyncio.Event()
    runs = [0]
    errors: list[Exception] = []

    async def flaky():
        runs[0] += 1
        if runs[0] < 3:
            raise ConnectionError("dropped")
        stop.set()  # third run "works" until told to stop
        return

    await asyncio.wait_for(
        supervise("t", flaky, stop=stop, backoff=_INSTANT, on_error=errors.append), timeout=2
    )

    assert runs[0] == 3
    assert len(errors) == 2


async def test_a_clean_return_is_never_restarted():
    runs = [0]

    async def once():
        runs[0] += 1

    await asyncio.wait_for(supervise("t", once, stop=asyncio.Event(), backoff=_INSTANT), timeout=1)

    assert runs[0] == 1


async def test_stop_during_backoff_exits_without_another_run():
    stop = asyncio.Event()
    runs = [0]

    async def crash():
        runs[0] += 1
        stop.set()
        raise RuntimeError("x")

    slow = AdaptiveInterval(
        PollingConfig(
            base_interval=3600, max_quiet_interval=3600, max_backoff_interval=3600, jitter_ratio=0.0
        )
    )
    await asyncio.wait_for(supervise("t", crash, stop=stop, backoff=slow), timeout=1)

    assert runs[0] == 1


async def test_cancellation_propagates():
    async def forever():
        await asyncio.sleep(3600)

    task = asyncio.create_task(supervise("t", forever, stop=asyncio.Event(), backoff=_INSTANT))
    await asyncio.sleep(0.01)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


async def test_a_long_healthy_run_resets_the_backoff():
    stop = asyncio.Event()
    now = [0.0]
    backoff = AdaptiveInterval(
        PollingConfig(
            base_interval=0.001,
            max_quiet_interval=0.001,
            max_backoff_interval=0.005,
            jitter_ratio=0.0,
        )
    )
    backoff.record_failure()
    backoff.record_failure()
    assert backoff.consecutive_failures == 2
    runs = [0]

    async def ran_long_then_crashed():
        runs[0] += 1
        if runs[0] == 1:
            now[0] += 120  # ran for 2 minutes before dying
            raise RuntimeError("late crash")
        stop.set()

    await asyncio.wait_for(
        supervise("t", ran_long_then_crashed, stop=stop, backoff=backoff, clock=lambda: now[0]),
        timeout=1,
    )

    assert backoff.consecutive_failures == 1  # reset to 0, then this crash made it 1
