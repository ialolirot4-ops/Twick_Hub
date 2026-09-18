"""Implements ``domain.protocols.DownloadEngine`` — the concrete FASE 7
download engine that ``EnqueueDownloadUseCase``/``CancelDownloadUseCase``
(FASE 3, application/downloads.py) were already built against, satisfied
structurally without either use case changing a single line.

Owns the per-job cancel/pause control state (``JobControlStore``) and the
``DownloadCoordinator``'s worker pool lifecycle. Pause/resume aren't part
of ``DownloadEngine`` (Master Plan §44 doesn't ask for that at the
Application-use-case level yet — see docs/risk-register.md) but are
exposed here for whatever calls this concretely, and are what the
"pausas" tests in this phase exercise directly.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol, runtime_checkable

from twick_hub.domain.downloads import DownloadJob
from twick_hub.domain.enums import DownloadStatus
from twick_hub.domain.protocols import DownloadRepository
from twick_hub.infrastructure.downloads.download_queue import DownloadQueue
from twick_hub.infrastructure.downloads.progress_tracker import ProgressTracker


@runtime_checkable
class Coordinator(Protocol):
    """What ``DownloadService`` needs from ``DownloadCoordinator`` — a
    Protocol so tests can substitute a fake without spinning up real
    worker tasks, the same way every other cross-component seam in this
    package (``SegmentFetcher``, ``ProcessRunner``, ``HlsReader``) does.
    """

    def start(self) -> None: ...

    async def stop(self) -> None: ...


class JobControlStore:
    """Shared, mutable cancel/pause flags per download id. Exists so
    ``DownloadService`` (writes, via ``cancel``/``pause``/``resume``) and
    ``DownloadCoordinator`` (reads, via the ``is_cancelled``/``is_paused``
    callables it hands each ``DownloadExecutor.run()`` call) don't need a
    circular dependency on each other — both just depend on this."""

    def __init__(self) -> None:
        self._cancelled: set[str] = set()
        self._paused: set[str] = set()

    def cancel(self, download_id: str) -> None:
        self._cancelled.add(download_id)

    def pause(self, download_id: str) -> None:
        self._paused.add(download_id)

    def resume(self, download_id: str) -> None:
        self._paused.discard(download_id)

    def is_cancelled(self, download_id: str) -> bool:
        return download_id in self._cancelled

    def is_paused(self, download_id: str) -> bool:
        return download_id in self._paused

    def forget(self, download_id: str) -> None:
        self._cancelled.discard(download_id)
        self._paused.discard(download_id)


class DownloadService:
    def __init__(
        self,
        downloads: DownloadRepository,
        progress: ProgressTracker,
        queue: DownloadQueue,
        coordinator: Coordinator,
        control: JobControlStore,
    ) -> None:
        self._downloads = downloads
        self._progress = progress
        self._queue = queue
        self._coordinator = coordinator
        self._control = control

    def start(self) -> None:
        self._coordinator.start()

    async def stop(self) -> None:
        await self._coordinator.stop()

    # --- DownloadEngine protocol -------------------------------------------------

    async def enqueue(self, job: DownloadJob) -> None:
        self._control.forget(job.download_id)
        self._coordinator.start()  # idempotent — safe even if start() wasn't called explicitly
        await self._queue.put(job.download_id)

    async def cancel(self, job_id: str) -> None:
        self._control.cancel(job_id)

    async def progress_of(self, job_id: str) -> float:
        return self._progress.progress_of(job_id)

    # --- pause/resume -------------------------------------------------

    async def pause(self, download_id: str) -> None:
        download = await self._downloads.get(download_id)
        if download is None or download.status not in (
            DownloadStatus.PREPARING,
            DownloadStatus.DOWNLOADING,
        ):
            return
        self._control.pause(download_id)
        await self._downloads.save(replace(download, status=DownloadStatus.PAUSED))

    async def resume(self, download_id: str) -> None:
        download = await self._downloads.get(download_id)
        if download is None or download.status != DownloadStatus.PAUSED:
            return
        self._control.resume(download_id)
        await self._downloads.save(replace(download, status=DownloadStatus.DOWNLOADING))
