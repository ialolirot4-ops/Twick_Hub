"""Orchestrates check → download → install → (rollback if needed) — the
``UpdateService`` Master Plan §51 asks for, gluing the other three
pieces (``UpdateChecker``, ``infrastructure.updates.UpdateDownloader``,
an ``UpdateInstaller``) together and persisting one ``UpdateAttempt`` per
cycle so "errores" and "rollback cuando sea viable" are inspectable after
the fact — including after a restart, if the app itself needed
relaunching mid-update (an actual relaunch mechanism is a packaging
concern, deferred with the rest of FASE 19 — see docs/architecture-
decisions.md's FASE 14 entry).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from twick_hub.application.updates.checker import UpdateChecker, UpdateCheckResult
from twick_hub.domain.enums import DownloadStatus, UpdateStatus
from twick_hub.domain.protocols import (
    DownloadRepository,
    UpdateArtifactDownloader,
    UpdateAttemptRepository,
    UpdateInstaller,
)
from twick_hub.domain.updates import DownloadsInProgressError, UpdateAttempt, UpdateInfo
from twick_hub.infrastructure.updates.installer import InstallError

_IN_FLIGHT = (
    DownloadStatus.QUEUED,
    DownloadStatus.PREPARING,
    DownloadStatus.DOWNLOADING,
    DownloadStatus.PROCESSING,
    DownloadStatus.PAUSED,
)


class UpdateService:
    def __init__(
        self,
        checker: UpdateChecker,
        downloader: UpdateArtifactDownloader,
        installer: UpdateInstaller,
        attempts: UpdateAttemptRepository,
        downloads: DownloadRepository,
        artifact_dir: Path,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._checker = checker
        self._downloader = downloader
        self._installer = installer
        self._attempts = attempts
        self._downloads = downloads
        self._artifact_dir = artifact_dir
        self._clock = clock

    async def check(self) -> UpdateCheckResult:
        return await self._checker.check()

    async def prepare(self, info: UpdateInfo) -> UpdateAttempt:
        """Downloads and integrity-checks the artifact for ``info``,
        persisting an ``UpdateAttempt`` throughout. Does *not* install —
        downloading never conflicts with the user's own downloads (a
        separate HTTP client, see ``UpdateDownloader``'s docstring), so
        nothing here needs to check for those."""
        now = self._clock()
        attempt = UpdateAttempt(
            from_version=self._checker.current_version,
            to_version=info.version,
            download_url=info.download_url,
            sha256=info.sha256,
            status=UpdateStatus.DOWNLOADING,
            started_at=now,
        )
        await self._attempts.save(attempt)

        destination = self._artifact_dir / f"{attempt.id}.zip"
        try:
            await self._downloader.download(info, destination)
        except Exception as exc:
            attempt = attempt.advanced(
                UpdateStatus.FAILED, now=self._clock(), error_message=str(exc)
            )
            await self._attempts.save(attempt)
            raise

        attempt = attempt.advanced(
            UpdateStatus.READY_TO_INSTALL, now=self._clock(), artifact_path=str(destination)
        )
        await self._attempts.save(attempt)
        return attempt

    async def install(self, attempt: UpdateAttempt) -> UpdateAttempt:
        """Refuses to run while any download is in flight (Master Plan
        §51: "No interferir con descargas activas") — raises
        ``DownloadsInProgressError`` rather than queueing or waiting, so
        the caller decides when it's safe to retry."""
        if attempt.artifact_path is None:
            raise ValueError("attempt has no downloaded artifact to install")
        artifact_path = attempt.artifact_path
        in_flight = await self._downloads.list_by_status(_IN_FLIGHT)
        if in_flight:
            raise DownloadsInProgressError(
                f"{len(in_flight)} download(s) in progress; try again once they finish"
            )

        attempt = attempt.advanced(UpdateStatus.INSTALLING, now=self._clock())
        await self._attempts.save(attempt)
        try:
            await self._installer.install(artifact_path)
        except InstallError as exc:
            attempt = attempt.advanced(
                UpdateStatus.FAILED, now=self._clock(), error_message=str(exc)
            )
            await self._attempts.save(attempt)
            raise
        attempt = attempt.advanced(UpdateStatus.INSTALLED, now=self._clock())
        await self._attempts.save(attempt)
        return attempt

    async def rollback(self, attempt: UpdateAttempt) -> UpdateAttempt:
        await self._installer.rollback()
        attempt = attempt.advanced(UpdateStatus.ROLLED_BACK, now=self._clock())
        await self._attempts.save(attempt)
        return attempt
