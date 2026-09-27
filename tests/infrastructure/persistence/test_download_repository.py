from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from sqlalchemy.orm import sessionmaker

from twick_hub.domain.downloads import Download
from twick_hub.domain.enums import DownloadStatus, MediaKind, Platform
from twick_hub.domain.value_objects import Duration, Media, PlatformRef
from twick_hub.infrastructure.persistence.download_repository import SqlDownloadRepository


def _download(external_id: str = "v1", created_at: datetime | None = None) -> Download:
    media = Media(
        kind=MediaKind.VIDEO,
        ref=PlatformRef(platform=Platform.TWITCH, external_id=external_id),
        title="A VOD",
        channel_ref=PlatformRef(platform=Platform.TWITCH, external_id="chan1"),
        thumbnail_url="https://example.invalid/thumb.jpg",
        duration=Duration(total_seconds=3600),
    )
    return Download(
        media=media,
        destination_path="/tmp/out.mp4",
        quality_label="source",
        created_at=created_at or datetime.now(),
    )


async def test_get_returns_none_when_absent(session_factory: sessionmaker):
    repo = SqlDownloadRepository(session_factory)
    assert await repo.get("nope") is None


async def test_save_then_get_round_trips_every_field_including_nested_media(
    session_factory: sessionmaker,
):
    repo = SqlDownloadRepository(session_factory)
    download = replace(
        _download(),
        status=DownloadStatus.COMPLETED,
        progress_percent=100.0,
        completed_at=datetime(2026, 1, 1, 12, 0, 0),
        file_size_bytes=123456,
    )

    await repo.save(download)
    fetched = await repo.get(download.id)

    assert fetched == download


async def test_save_round_trips_a_download_with_no_channel_ref_or_duration(
    session_factory: sessionmaker,
):
    repo = SqlDownloadRepository(session_factory)
    ref = PlatformRef(platform=Platform.KICK, external_id="clip1")
    media = Media(kind=MediaKind.CLIP, ref=ref, title="Clip")
    download = Download(media=media, destination_path="/tmp/clip.mp4", quality_label="source")

    await repo.save(download)
    fetched = await repo.get(download.id)

    assert fetched == download
    assert fetched is not None
    assert fetched.media.channel_ref is None
    assert fetched.media.duration is None


async def test_save_upserts_status_transitions_by_id(session_factory: sessionmaker):
    repo = SqlDownloadRepository(session_factory)
    download = _download()
    await repo.save(download)

    downloading = replace(download, status=DownloadStatus.DOWNLOADING)
    await repo.save(downloading)
    failed = replace(downloading, status=DownloadStatus.FAILED, error_message="segment 3 failed")
    await repo.save(failed)

    fetched = await repo.get(download.id)
    assert fetched is not None
    assert fetched.status == DownloadStatus.FAILED
    assert fetched.error_message == "segment 3 failed"
    assert len(await repo.list_all()) == 1


async def test_list_all_orders_most_recently_created_first(session_factory: sessionmaker):
    repo = SqlDownloadRepository(session_factory)
    base = datetime(2026, 1, 1)
    older = _download("v1", base)
    newer = _download("v2", base + timedelta(hours=1))

    await repo.save(older)
    await repo.save(newer)

    result = await repo.list_all()
    assert [d.id for d in result] == [newer.id, older.id]


async def test_list_all_respects_limit_and_offset(session_factory: sessionmaker):
    repo = SqlDownloadRepository(session_factory)
    base = datetime(2026, 1, 1)
    for i in range(5):
        await repo.save(_download(f"v{i}", base + timedelta(minutes=i)))

    page = await repo.list_all(limit=2, offset=1)

    assert [d.media.ref.external_id for d in page] == ["v3", "v2"]
