import pytest

from tests.application.fakes import (
    FakeDownloadEngine,
    FakePlaybackResolver,
    InMemoryDownloadRepository,
)
from twick_hub.application.downloads import (
    CancelDownloadUseCase,
    EnqueueDownloadUseCase,
    QualityNotAvailableError,
)
from twick_hub.domain.enums import DownloadStatus, MediaKind, Platform
from twick_hub.domain.value_objects import Media, PlatformRef

_MEDIA = Media(
    kind=MediaKind.VIDEO, ref=PlatformRef(platform=Platform.TWITCH, external_id="v1"), title="A VOD"
)


async def test_enqueue_download_saves_and_dispatches_to_the_engine():
    downloads = InMemoryDownloadRepository()
    engine = FakeDownloadEngine()
    use_case = EnqueueDownloadUseCase(
        playback=FakePlaybackResolver(), downloads=downloads, engine=engine
    )

    download = await use_case.execute(_MEDIA, "/tmp/out.mp4", "720p")

    assert download.status == DownloadStatus.PENDING
    assert await downloads.get(download.id) == download
    assert len(engine.enqueued) == 1
    assert engine.enqueued[0].download_id == download.id


async def test_enqueue_download_rejects_unavailable_quality():
    downloads = InMemoryDownloadRepository()
    engine = FakeDownloadEngine()
    use_case = EnqueueDownloadUseCase(
        playback=FakePlaybackResolver(qualities=["source"]), downloads=downloads, engine=engine
    )

    with pytest.raises(QualityNotAvailableError, match="1080p"):
        await use_case.execute(_MEDIA, "/tmp/out.mp4", "1080p")

    assert await downloads.list_all() == []
    assert engine.enqueued == []


async def test_cancel_download_marks_it_cancelled_and_tells_the_engine():
    downloads = InMemoryDownloadRepository()
    engine = FakeDownloadEngine()
    download = await EnqueueDownloadUseCase(
        playback=FakePlaybackResolver(), downloads=downloads, engine=engine
    ).execute(_MEDIA, "/tmp/out.mp4", "source")

    await CancelDownloadUseCase(downloads=downloads, engine=engine).execute(download.id)

    updated = await downloads.get(download.id)
    assert updated is not None
    assert updated.status == DownloadStatus.CANCELLED
    assert engine.cancelled == [download.id]


async def test_cancel_unknown_download_is_a_no_op():
    downloads = InMemoryDownloadRepository()
    engine = FakeDownloadEngine()

    await CancelDownloadUseCase(downloads=downloads, engine=engine).execute("does-not-exist")

    assert engine.cancelled == []
