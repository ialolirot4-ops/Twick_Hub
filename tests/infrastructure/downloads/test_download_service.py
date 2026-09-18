from __future__ import annotations

from tests.application.fakes import InMemoryDownloadRepository
from twick_hub.domain.downloads import Download, DownloadJob
from twick_hub.domain.enums import DownloadStatus, MediaKind, Platform
from twick_hub.domain.value_objects import Media, PlatformRef
from twick_hub.infrastructure.downloads.download_queue import DownloadQueue
from twick_hub.infrastructure.downloads.download_service import DownloadService, JobControlStore
from twick_hub.infrastructure.downloads.progress_tracker import ProgressTracker


class FakeCoordinator:
    def __init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0

    def start(self) -> None:
        self.start_calls += 1

    async def stop(self) -> None:
        self.stop_calls += 1


def _download(status: DownloadStatus = DownloadStatus.QUEUED) -> Download:
    ref = PlatformRef(platform=Platform.TWITCH, external_id="v1")
    media = Media(kind=MediaKind.VIDEO, ref=ref, title="A VOD")
    return Download(
        media=media, destination_path="/tmp/out.mp4", quality_label="source", status=status
    )


def _service(downloads=None, progress=None, coordinator=None, control=None) -> DownloadService:
    return DownloadService(
        downloads=downloads if downloads is not None else InMemoryDownloadRepository(),
        progress=progress if progress is not None else ProgressTracker(),
        queue=DownloadQueue(),
        coordinator=coordinator if coordinator is not None else FakeCoordinator(),
        control=control if control is not None else JobControlStore(),
    )


async def test_enqueue_puts_download_id_and_starts_coordinator():
    coordinator = FakeCoordinator()
    service = _service(coordinator=coordinator)

    await service.enqueue(DownloadJob(download_id="d1"))

    assert coordinator.start_calls == 1
    assert await service._queue.get() == "d1"  # noqa: SLF001 - verifying the queue side effect directly


async def test_enqueue_forgets_previous_cancel_and_pause_state():
    control = JobControlStore()
    control.cancel("d1")
    control.pause("d1")
    service = _service(control=control)

    await service.enqueue(DownloadJob(download_id="d1"))

    assert control.is_cancelled("d1") is False
    assert control.is_paused("d1") is False


async def test_cancel_marks_control_store():
    control = JobControlStore()
    service = _service(control=control)

    await service.cancel("d1")

    assert control.is_cancelled("d1") is True


async def test_progress_of_delegates_to_tracker():
    progress = ProgressTracker()
    progress.start("d1", total_segments=4)
    progress.advance("d1", by=1)
    service = _service(progress=progress)

    assert await service.progress_of("d1") == 25.0


async def test_pause_sets_status_paused_and_control_flag_when_downloading():
    downloads = InMemoryDownloadRepository()
    download = _download(status=DownloadStatus.DOWNLOADING)
    await downloads.save(download)
    control = JobControlStore()
    service = _service(downloads=downloads, control=control)

    await service.pause(download.id)

    updated = await downloads.get(download.id)
    assert updated is not None
    assert updated.status == DownloadStatus.PAUSED
    assert control.is_paused(download.id) is True


async def test_pause_is_a_noop_for_a_terminal_status():
    downloads = InMemoryDownloadRepository()
    download = _download(status=DownloadStatus.COMPLETED)
    await downloads.save(download)
    control = JobControlStore()
    service = _service(downloads=downloads, control=control)

    await service.pause(download.id)

    updated = await downloads.get(download.id)
    assert updated is not None
    assert updated.status == DownloadStatus.COMPLETED
    assert control.is_paused(download.id) is False


async def test_pause_unknown_download_is_a_noop():
    service = _service()
    await service.pause("does-not-exist")  # must not raise


async def test_resume_sets_status_back_to_downloading():
    downloads = InMemoryDownloadRepository()
    download = _download(status=DownloadStatus.PAUSED)
    await downloads.save(download)
    control = JobControlStore()
    control.pause(download.id)
    service = _service(downloads=downloads, control=control)

    await service.resume(download.id)

    updated = await downloads.get(download.id)
    assert updated is not None
    assert updated.status == DownloadStatus.DOWNLOADING
    assert control.is_paused(download.id) is False


async def test_resume_is_a_noop_unless_currently_paused():
    downloads = InMemoryDownloadRepository()
    download = _download(status=DownloadStatus.DOWNLOADING)
    await downloads.save(download)
    service = _service(downloads=downloads)

    await service.resume(download.id)

    updated = await downloads.get(download.id)
    assert updated is not None
    assert updated.status == DownloadStatus.DOWNLOADING  # unchanged, not re-saved as something odd


async def test_stop_delegates_to_coordinator():
    coordinator = FakeCoordinator()
    service = _service(coordinator=coordinator)

    await service.stop()

    assert coordinator.stop_calls == 1
