from __future__ import annotations

import asyncio
from pathlib import Path

from tests.application.fakes import InMemoryFavoriteRepository
from tests.application.live_monitor.fakes import stream_of
from tests.application.scheduling.env import CHANNEL, Env
from twick_hub.application.scheduling.auto_download import AutoDownloadService
from twick_hub.application.scheduling.retry import RetryPolicy
from twick_hub.domain.collections import Favorite
from twick_hub.domain.enums import DownloadStatus
from twick_hub.domain.events import ChannelWentOffline, ChannelWentOnline, DownloadFinished


class _Service:
    """AutoDownloadService wired to a test Env, with sleeping made
    instantaneous and recorded."""

    def __init__(self, *, max_attempts: int = 3) -> None:
        self.env = Env()
        self.favorites = InMemoryFavoriteRepository()
        self.delays: list[float] = []

        async def sleep(delay: float) -> None:
            self.delays.append(delay)

        self.service = AutoDownloadService(
            self.favorites,
            self.env.recorder,
            retry=RetryPolicy(base_delay_seconds=10, factor=2, max_delay_seconds=100),
            max_attempts=max_attempts,
            sleep=sleep,
        )
        self.service.attach(self.env.bus)

    async def favorite(self, **fields) -> Favorite:
        favorite = Favorite(channel_ref=CHANNEL, auto_download=True, **fields)
        await self.favorites.save(favorite)
        return favorite

    async def online(self, *, initial: bool = False) -> None:
        await self.env.go_live()
        await self.env.bus.publish(ChannelWentOnline(CHANNEL, stream_of(CHANNEL), initial=initial))
        await self.service.wait_idle()

    async def settle_retries(self) -> None:
        for _ in range(5):
            await asyncio.sleep(0)
            await self.service.wait_idle()


async def test_records_a_favorite_with_auto_download_on_when_it_goes_live():
    t = _Service()
    await t.favorite(
        preferred_quality="720p", preferred_format="mkv", download_directory="/fav", position=2
    )

    await t.online()

    (download,) = await t.env.downloads.list_all()
    assert download.quality_label == "720p60"
    assert download.destination_path == str(Path("/fav/streamer/Big Stream (2026-09-21).mkv"))
    assert [job.priority for job in t.env.engine.enqueued] == [2]  # the favorite's position


async def test_a_stream_already_live_at_startup_is_recorded_too():
    t = _Service()
    await t.favorite()

    await t.online(initial=True)

    assert len(t.env.engine.enqueued) == 1


async def test_a_favorite_with_auto_download_off_is_not_recorded():
    t = _Service()
    await t.favorites.save(Favorite(channel_ref=CHANNEL, auto_download=False, notify_on_live=True))

    await t.online()

    assert t.env.engine.enqueued == []


async def test_a_channel_that_is_not_a_favorite_is_ignored():
    t = _Service()

    await t.online()

    assert t.env.engine.enqueued == []


async def test_repeated_go_live_events_do_not_start_a_second_recording():
    t = _Service()
    await t.favorite()
    await t.online()

    await t.env.bus.publish(ChannelWentOnline(CHANNEL, stream_of(CHANNEL)))
    await t.service.wait_idle()

    assert len(t.env.engine.enqueued) == 1


async def test_a_go_live_event_for_a_channel_that_already_went_offline_records_nothing():
    t = _Service()
    await t.favorite()
    await t.env.bus.publish(
        ChannelWentOnline(CHANNEL, stream_of(CHANNEL))
    )  # live provider says offline
    await t.service.wait_idle()

    assert t.env.engine.enqueued == []


async def test_a_failed_recording_is_retried_with_backoff_until_the_limit():
    t = _Service(max_attempts=3)
    await t.favorite()
    await t.online()

    for _ in range(2):  # two failures → two retries
        (download_id,) = {d for d in t.service._owned}  # the recording currently owned
        await t.env.finish(download_id, DownloadStatus.FAILED, "network")
        await t.settle_retries()

    assert t.delays == [10, 20]
    assert len(t.env.engine.enqueued) == 3

    (download_id,) = {d for d in t.service._owned}
    await t.env.finish(download_id, DownloadStatus.FAILED, "network")  # third failure: give up
    await t.settle_retries()

    assert len(t.env.engine.enqueued) == 3
    assert t.delays == [10, 20]


async def test_a_completed_recording_is_not_retried_and_resets_the_failure_count():
    t = _Service(max_attempts=2)
    await t.favorite()
    await t.online()
    (first,) = set(t.service._owned)
    await t.env.finish(first, DownloadStatus.FAILED, "glitch")
    await t.settle_retries()
    (second,) = set(t.service._owned)

    await t.env.finish(second, DownloadStatus.COMPLETED)
    await t.settle_retries()

    assert len(t.env.engine.enqueued) == 2
    assert t.service._failures == {}


async def test_a_cancelled_recording_is_not_retried():
    t = _Service()
    await t.favorite()
    await t.online()
    (download_id,) = set(t.service._owned)

    await t.env.finish(download_id, DownloadStatus.CANCELLED)
    await t.settle_retries()

    assert len(t.env.engine.enqueued) == 1


async def test_someone_elses_download_finishing_is_ignored():
    t = _Service()
    await t.favorite()

    await t.env.bus.publish(DownloadFinished("not-mine", DownloadStatus.FAILED, "x"))
    await t.service.wait_idle()

    assert t.delays == []


async def test_a_start_failure_is_retried_too():
    t = _Service()
    await t.favorite()
    calls = [0]
    real_enqueue = t.env.engine.enqueue

    async def flaky(job):
        calls[0] += 1
        if calls[0] == 1:
            raise ConnectionError("engine hiccup")
        await real_enqueue(job)

    t.env.engine.enqueue = flaky  # type: ignore[method-assign]

    await t.online()
    await t.settle_retries()

    assert t.delays == [10]
    assert len(t.env.engine.enqueued) == 1


async def test_the_stream_ending_cancels_a_pending_retry_and_resets_the_count():
    t = _Service()
    await t.favorite()
    gate = asyncio.Event()

    async def blocked_sleep(delay: float) -> None:
        await gate.wait()

    t.service._sleep = blocked_sleep
    await t.online()
    (download_id,) = set(t.service._owned)
    await t.env.finish(download_id, DownloadStatus.FAILED, "x")
    await asyncio.sleep(0)
    assert t.service._retry_tasks  # a retry is waiting

    await t.env.bus.publish(ChannelWentOffline(CHANNEL))
    await t.service.wait_idle()

    assert not t.service._retry_tasks
    assert t.service._failures == {}


async def test_stop_cancels_pending_retries():
    t = _Service()
    await t.favorite()

    async def forever(delay: float) -> None:
        await asyncio.sleep(3600)

    t.service._sleep = forever
    await t.online()
    (download_id,) = set(t.service._owned)
    await t.env.finish(download_id, DownloadStatus.FAILED, "x")
    await asyncio.sleep(0)

    await asyncio.wait_for(t.service.stop(), timeout=1)

    assert not t.service._retry_tasks
