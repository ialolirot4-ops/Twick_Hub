from __future__ import annotations

from tests.application.fakes import FakeDownloadEngine, InMemoryDownloadRepository
from twick_hub.application.scheduling.recovery import (
    INTERRUPTED_MESSAGE,
    RecoverInterruptedDownloadsUseCase,
)
from twick_hub.domain.downloads import Download
from twick_hub.domain.enums import DownloadStatus, MediaKind, Platform
from twick_hub.domain.value_objects import Media, PlatformRef


def _download(kind: MediaKind, status: DownloadStatus) -> Download:
    ref = PlatformRef(platform=Platform.TWITCH, external_id=f"{kind}-{status}")
    media = Media(kind=kind, ref=ref, title="t")
    return Download(media=media, destination_path="/x.mp4", quality_label="720p60", status=status)


async def _run(*downloads: Download):
    repo = InMemoryDownloadRepository()
    engine = FakeDownloadEngine()
    for download in downloads:
        await repo.save(download)
    report = await RecoverInterruptedDownloadsUseCase(repo, engine).execute()
    return repo, engine, report


async def test_interrupted_live_captures_are_marked_failed_with_the_reason():
    stream = _download(MediaKind.STREAM, DownloadStatus.DOWNLOADING)

    repo, engine, report = await _run(stream)

    saved = await repo.get(stream.id)
    assert saved is not None
    assert saved.status is DownloadStatus.FAILED and saved.error_message == INTERRUPTED_MESSAGE
    assert report.failed_streams == (stream.id,)
    assert engine.enqueued == []  # a finished live stream cannot be resumed


async def test_interrupted_vods_and_clips_are_requeued():
    vod = _download(MediaKind.VIDEO, DownloadStatus.DOWNLOADING)
    clip = _download(MediaKind.CLIP, DownloadStatus.PROCESSING)

    repo, engine, report = await _run(vod, clip)

    assert {job.download_id for job in engine.enqueued} == {vod.id, clip.id}
    assert set(report.requeued) == {vod.id, clip.id}
    for download in (vod, clip):
        saved = await repo.get(download.id)
        assert saved is not None and saved.status is DownloadStatus.QUEUED


async def test_every_in_flight_state_counts_as_interrupted():
    statuses = (
        DownloadStatus.QUEUED,
        DownloadStatus.PREPARING,
        DownloadStatus.DOWNLOADING,
        DownloadStatus.PROCESSING,
    )
    downloads = [_download(MediaKind.VIDEO, status) for status in statuses]

    _, engine, report = await _run(*downloads)

    assert len(report.requeued) == len(statuses)
    assert len(engine.enqueued) == len(statuses)


async def test_paused_and_finished_downloads_are_left_alone():
    paused = _download(MediaKind.VIDEO, DownloadStatus.PAUSED)
    done = _download(MediaKind.VIDEO, DownloadStatus.COMPLETED)
    failed = _download(MediaKind.STREAM, DownloadStatus.FAILED)
    cancelled = _download(MediaKind.VIDEO, DownloadStatus.CANCELLED)

    repo, engine, report = await _run(paused, done, failed, cancelled)

    assert engine.enqueued == [] and report == report.__class__()
    for original in (paused, done, failed, cancelled):
        assert await repo.get(original.id) == original


async def test_nothing_to_recover_is_a_noop():
    _, engine, report = await _run()
    assert engine.enqueued == [] and report.failed_streams == () and report.requeued == ()
