from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pytest

from tests.application.fakes import InMemoryDownloadRepository, InMemoryUpdateAttemptRepository
from twick_hub.application.updates.checker import UpdateChecker
from twick_hub.application.updates.service import UpdateService
from twick_hub.domain.downloads import Download
from twick_hub.domain.enums import DownloadStatus, MediaKind, Platform, UpdateStatus
from twick_hub.domain.updates import DownloadsInProgressError, UpdateInfo
from twick_hub.domain.value_objects import Media, PlatformRef
from twick_hub.domain.version import Version
from twick_hub.infrastructure.updates.installer import InstallError

_SHA = "d" * 64


def _info(version: str = "1.1.0") -> UpdateInfo:
    return UpdateInfo(
        version=Version.parse(version),
        download_url="https://example.invalid/u.zip",
        sha256=_SHA,
        size_bytes=100,
    )


@dataclass
class _FakeDownloader:
    written: bytes = b"fake artifact bytes"
    fail_with: Exception | None = None
    calls: list = field(default_factory=list)

    async def download(self, info: UpdateInfo, destination: Path) -> Path:
        self.calls.append((info, destination))
        if self.fail_with is not None:
            raise self.fail_with
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.written)
        return destination


@dataclass
class _FakeInstaller:
    fail_with: Exception | None = None
    installed: list = field(default_factory=list)
    rolled_back: bool = False

    async def install(self, artifact_path: str) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.installed.append(artifact_path)

    async def rollback(self) -> None:
        self.rolled_back = True


class _FrozenClock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now


def _service(tmp_path: Path, downloader=None, installer=None, downloads=None, attempts=None):
    checker = UpdateChecker(source=None, current_version=Version.parse("1.0.0"))  # type: ignore[arg-type]
    return UpdateService(
        checker=checker,
        downloader=downloader or _FakeDownloader(),
        installer=installer or _FakeInstaller(),
        attempts=attempts or InMemoryUpdateAttemptRepository(),
        downloads=downloads or InMemoryDownloadRepository(),
        artifact_dir=tmp_path / "artifacts",
        clock=_FrozenClock(datetime(2026, 9, 24, 10, 0)),
    )


def _download(status: DownloadStatus) -> Download:
    media = Media(
        kind=MediaKind.VIDEO,
        ref=PlatformRef(platform=Platform.TWITCH, external_id="v1"),
        title="t",
    )
    return Download(media=media, destination_path="/x.mp4", quality_label="best", status=status)


# --- prepare (download + verify) --------------------------------------------


async def test_prepare_downloads_and_marks_ready_to_install(tmp_path: Path):
    attempts = InMemoryUpdateAttemptRepository()
    service = _service(tmp_path, attempts=attempts)

    attempt = await service.prepare(_info())

    assert attempt.status is UpdateStatus.READY_TO_INSTALL
    assert attempt.artifact_path is not None
    assert Path(attempt.artifact_path).exists()
    stored = await attempts.get(attempt.id)
    assert stored == attempt


async def test_prepare_records_intermediate_downloading_status_before_finishing(tmp_path: Path):
    attempts = InMemoryUpdateAttemptRepository()
    service = _service(tmp_path, attempts=attempts)

    await service.prepare(_info())

    all_attempts = await attempts.list_all()
    assert len(all_attempts) == 1  # same attempt row updated in place, not duplicated


async def test_a_failed_download_marks_the_attempt_failed_and_reraises(tmp_path: Path):
    attempts = InMemoryUpdateAttemptRepository()
    downloader = _FakeDownloader(fail_with=ConnectionError("network down"))
    service = _service(tmp_path, downloader=downloader, attempts=attempts)

    with pytest.raises(ConnectionError):
        await service.prepare(_info())

    (stored,) = await attempts.list_all()
    assert stored.status is UpdateStatus.FAILED
    assert stored.error_message == "network down"


async def test_prepare_records_from_and_to_version(tmp_path: Path):
    attempt = await _service(tmp_path).prepare(_info("2.0.0"))
    assert (str(attempt.from_version), str(attempt.to_version)) == ("1.0.0", "2.0.0")


# --- install ------------------------------------------------------------


async def test_install_calls_the_installer_and_marks_installed(tmp_path: Path):
    attempts = InMemoryUpdateAttemptRepository()
    installer = _FakeInstaller()
    service = _service(tmp_path, installer=installer, attempts=attempts)
    attempt = await service.prepare(_info())

    installed = await service.install(attempt)

    assert installed.status is UpdateStatus.INSTALLED
    assert installed.finished_at is not None
    assert installer.installed == [attempt.artifact_path]


async def test_install_refuses_while_downloads_are_in_flight(tmp_path: Path):
    downloads = InMemoryDownloadRepository()
    await downloads.save(_download(DownloadStatus.DOWNLOADING))
    service = _service(tmp_path, downloads=downloads)
    attempt = await service.prepare(_info())

    with pytest.raises(DownloadsInProgressError):
        await service.install(attempt)


@pytest.mark.parametrize(
    "status",
    [
        DownloadStatus.QUEUED,
        DownloadStatus.PREPARING,
        DownloadStatus.PROCESSING,
        DownloadStatus.PAUSED,
    ],
)
async def test_install_refuses_for_every_in_flight_download_status(tmp_path: Path, status):
    downloads = InMemoryDownloadRepository()
    await downloads.save(_download(status))
    service = _service(tmp_path, downloads=downloads)
    attempt = await service.prepare(_info())

    with pytest.raises(DownloadsInProgressError):
        await service.install(attempt)


@pytest.mark.parametrize(
    "status", [DownloadStatus.COMPLETED, DownloadStatus.FAILED, DownloadStatus.CANCELLED]
)
async def test_install_proceeds_when_downloads_are_only_in_terminal_states(tmp_path: Path, status):
    downloads = InMemoryDownloadRepository()
    await downloads.save(_download(status))
    service = _service(tmp_path, downloads=downloads)
    attempt = await service.prepare(_info())

    installed = await service.install(attempt)

    assert installed.status is UpdateStatus.INSTALLED


async def test_install_without_a_downloaded_artifact_raises():
    from twick_hub.domain.updates import UpdateAttempt

    service = _service(Path("/tmp"))
    never_prepared = UpdateAttempt(
        from_version=Version.parse("1.0.0"),
        to_version=Version.parse("1.1.0"),
        download_url="https://example.invalid/u.zip",
        sha256=_SHA,
    )

    with pytest.raises(ValueError, match="no downloaded artifact"):
        await service.install(never_prepared)


async def test_a_failed_install_marks_the_attempt_failed_and_reraises(tmp_path: Path):
    attempts = InMemoryUpdateAttemptRepository()
    installer = _FakeInstaller(fail_with=InstallError("disk full"))
    service = _service(tmp_path, installer=installer, attempts=attempts)
    attempt = await service.prepare(_info())

    with pytest.raises(InstallError):
        await service.install(attempt)

    stored = await attempts.get(attempt.id)
    assert stored is not None
    assert stored.status is UpdateStatus.FAILED and stored.error_message == "disk full"


# --- rollback -------------------------------------------------------------


async def test_rollback_calls_the_installer_and_marks_rolled_back(tmp_path: Path):
    attempts = InMemoryUpdateAttemptRepository()
    installer = _FakeInstaller()
    service = _service(tmp_path, installer=installer, attempts=attempts)
    attempt = await service.prepare(_info())
    installed = await service.install(attempt)

    rolled_back = await service.rollback(installed)

    assert rolled_back.status is UpdateStatus.ROLLED_BACK
    assert installer.rolled_back is True
