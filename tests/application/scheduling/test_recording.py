from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tests.application.scheduling.env import CHANNEL, OTHER, Env
from twick_hub.application.scheduling.recording import (
    AlreadyRecordingError,
    ChannelNotLiveError,
    RecordingRequest,
    RecordingUnavailableError,
)
from twick_hub.domain.enums import DownloadStatus, MediaKind
from twick_hub.domain.events import DownloadFinished


async def test_records_a_live_channel():
    env = Env()
    await env.go_live()

    download = await env.recorder.start(RecordingRequest(CHANNEL, quality="720p", priority=4))

    assert download.media.kind is MediaKind.STREAM
    assert download.media.channel_ref == CHANNEL
    assert download.quality_label == "720p60"  # the real label, never the preference
    assert download.status is DownloadStatus.QUEUED
    assert download.destination_path == str(Path("/rec/streamer/Big Stream (2026-09-21).mp4"))
    assert await env.downloads.get(download.id) == download
    assert [(job.download_id, job.priority) for job in env.engine.enqueued] == [(download.id, 4)]
    assert env.recorder.active_download_of(CHANNEL) == download.id


async def test_an_offline_channel_is_not_recorded_and_leaves_no_trace():
    env = Env()

    with pytest.raises(ChannelNotLiveError):
        await env.recorder.start(RecordingRequest(CHANNEL))

    assert await env.downloads.list_all() == []
    assert env.engine.enqueued == []


async def test_a_second_request_for_the_same_channel_reports_the_first_download():
    env = Env()
    await env.go_live()
    first = await env.recorder.start(RecordingRequest(CHANNEL))

    with pytest.raises(AlreadyRecordingError) as info:
        await env.recorder.start(RecordingRequest(CHANNEL))

    assert info.value.download_id == first.id
    assert len(env.engine.enqueued) == 1


async def test_two_simultaneous_requests_produce_one_recording():
    env = Env()
    await env.go_live()

    results = await asyncio.gather(
        env.recorder.start(RecordingRequest(CHANNEL)),
        env.recorder.start(RecordingRequest(CHANNEL)),
        return_exceptions=True,
    )

    assert sum(not isinstance(r, Exception) for r in results) == 1
    assert sum(isinstance(r, AlreadyRecordingError) for r in results) == 1
    assert len(env.engine.enqueued) == 1


@pytest.mark.parametrize(
    "status", [DownloadStatus.COMPLETED, DownloadStatus.FAILED, DownloadStatus.CANCELLED]
)
async def test_the_channel_is_free_again_once_its_download_finishes(status):
    env = Env()
    await env.go_live()
    first = await env.recorder.start(RecordingRequest(CHANNEL))

    await env.bus.publish(DownloadFinished(first.id, status))

    assert env.recorder.active_download_of(CHANNEL) is None
    second = await env.recorder.start(RecordingRequest(CHANNEL))
    assert second.id != first.id


async def test_another_downloads_ending_does_not_free_the_channel():
    env = Env()
    await env.go_live()
    first = await env.recorder.start(RecordingRequest(CHANNEL))

    await env.bus.publish(DownloadFinished("someone-else", DownloadStatus.COMPLETED))

    assert env.recorder.active_download_of(CHANNEL) == first.id


async def test_a_platform_that_offers_no_quality_is_unavailable_not_retryable():
    env = Env()
    env.resolver.qualities = []
    await env.go_live()

    with pytest.raises(RecordingUnavailableError):
        await env.recorder.start(RecordingRequest(CHANNEL))

    assert await env.downloads.list_all() == []


async def test_an_unavailable_preference_records_the_best_quality_instead():
    env = Env()
    await env.go_live()

    download = await env.recorder.start(RecordingRequest(CHANNEL, quality="1440p"))

    assert download.quality_label == "1080p60"


async def test_an_enqueue_failure_marks_the_download_failed_and_frees_the_channel():
    env = Env()
    await env.go_live()

    async def boom(job):
        raise RuntimeError("engine down")

    env.engine.enqueue = boom  # type: ignore[method-assign]

    with pytest.raises(RuntimeError):
        await env.recorder.start(RecordingRequest(CHANNEL))

    (saved,) = await env.downloads.list_all()
    assert saved.status is DownloadStatus.FAILED and saved.error_message == "engine down"
    assert env.recorder.active_download_of(CHANNEL) is None


async def test_downloads_in_flight_reserve_their_destinations():
    env = Env(template="{title}")  # every channel would pick the same path
    await env.go_live(CHANNEL)
    await env.go_live(OTHER)

    first = await env.recorder.start(RecordingRequest(CHANNEL))
    second = await env.recorder.start(RecordingRequest(OTHER))

    assert first.destination_path == str(Path("/rec/Big Stream.mp4"))
    assert second.destination_path == str(Path("/rec/Big Stream (2).mp4"))


async def test_a_missing_channel_name_falls_back_to_its_id():
    env = Env()
    env.directory.channels.clear()
    await env.go_live()

    download = await env.recorder.start(RecordingRequest(CHANNEL))

    assert Path(download.destination_path).parent.name == "1"


async def test_a_resolver_failure_propagates_and_records_nothing():
    env = Env()
    await env.go_live()

    async def broken(media):
        raise ConnectionError("network")

    env.resolver.available_qualities = broken  # type: ignore[method-assign]

    with pytest.raises(ConnectionError):
        await env.recorder.start(RecordingRequest(CHANNEL))

    assert await env.downloads.list_all() == []
