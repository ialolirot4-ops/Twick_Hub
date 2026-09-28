"""Builds the ``Container`` exactly once, in the right order.

Importing this module has no side effects — nothing runs, no Qt object
is created, no database connection is opened, until ``build_container()``
is actually called. This is the point of docs/architecture-decisions.md
AD-03: TwitchLink 3.5.5's ``Core/App.py`` does the opposite, creating
``Instance = App(...)`` as a side effect of import.
"""

from __future__ import annotations

from collections.abc import Mapping

import httpx

from twick_hub.application.platform_registry import PlatformAdapters, PlatformRegistry
from twick_hub.bootstrap.container import Container
from twick_hub.config.settings import AppConfig, load_config
from twick_hub.domain.enums import Platform
from twick_hub.infrastructure.downloads.download_coordinator import DownloadCoordinator
from twick_hub.infrastructure.downloads.download_executor import DownloadExecutor
from twick_hub.infrastructure.downloads.download_queue import DownloadQueue
from twick_hub.infrastructure.downloads.download_service import DownloadService, JobControlStore
from twick_hub.infrastructure.downloads.ffmpeg_processor import (
    AsyncioProcessRunner,
    FFmpegProcessor,
)
from twick_hub.infrastructure.downloads.hls import HlsPlaylistReader
from twick_hub.infrastructure.downloads.media_processor import MediaProcessor
from twick_hub.infrastructure.downloads.progress_tracker import ProgressTracker
from twick_hub.infrastructure.downloads.retry_policy import RetryPolicy
from twick_hub.infrastructure.downloads.segment_manager import HttpxSegmentFetcher, SegmentManager
from twick_hub.infrastructure.persistence.download_repository import SqlDownloadRepository
from twick_hub.infrastructure.persistence.engine import (
    build_engine,
    build_session_factory,
)
from twick_hub.infrastructure.persistence.favorite_repository import SqlFavoriteRepository
from twick_hub.infrastructure.persistence.notification_repository import SqlNotificationRepository
from twick_hub.infrastructure.persistence.scheduled_download_repository import (
    SqlScheduledDownloadRepository,
)
from twick_hub.logging_setup import configure_logging

# Master Plan §19 ("workers limitados"): matches DownloadCoordinator's own
# constructor default — spelled out here, not left implicit, since this is
# the one real call site that decides it (AD-36 left this open for FASE 7).
_DOWNLOAD_WORKER_COUNT = 3


def build_container(
    config: AppConfig | None = None,
    *,
    platform_adapters: Mapping[Platform, PlatformAdapters] | None = None,
) -> Container:
    """``platform_adapters`` (FASE 21c) are the real Twitch/Kick adapters
    from ``bootstrap/platforms.py``; they need a live Qt app, so the caller
    (``main()``) builds them and passes them in. Left unset, both platforms
    are registered with empty adapters — the FASE 21a behaviour, which is
    what every Qt-free caller (most tests) wants.
    """
    resolved_config = config or load_config()
    configure_logging(resolved_config)

    engine = build_engine(resolved_config)
    session_factory = build_session_factory(engine)

    favorites = SqlFavoriteRepository(session_factory)
    downloads = SqlDownloadRepository(session_factory)
    notifications = SqlNotificationRepository(session_factory)
    scheduled_downloads = SqlScheduledDownloadRepository(session_factory)

    # Both platforms are always registered — an absent adapter means "not
    # supported", never UnknownPlatformError (see PlatformRegistry's own
    # docstring). Anything passed in replaces that platform's empty default.
    platform_registry = PlatformRegistry(
        {
            Platform.TWITCH: PlatformAdapters(),
            Platform.KICK: PlatformAdapters(),
            **(platform_adapters or {}),
        }
    )

    download_service = _build_download_service(resolved_config, downloads, platform_registry)

    return Container(
        config=resolved_config,
        engine=engine,
        session_factory=session_factory,
        favorites=favorites,
        downloads=downloads,
        download_service=download_service,
        notifications=notifications,
        scheduled_downloads=scheduled_downloads,
        platform_registry=platform_registry,
    )


def _build_download_service(
    config: AppConfig,
    downloads: SqlDownloadRepository,
    registry: PlatformRegistry,
) -> DownloadService:
    """Assembles the real FASE 7 pipeline (RISK-ARCH-03/04): a
    ``DownloadQueue`` + ``JobControlStore`` feed a ``DownloadCoordinator``
    driving a ``DownloadExecutor``, the same wiring
    tests/test_playlist_download_integration.py already exercises with
    fakes standing in for the network/ffmpeg edges. What that test
    doesn't decide — because AD-36 deliberately left it open — is what
    this function commits to for a real run: ``_DOWNLOAD_WORKER_COUNT``
    workers, ``work_dir`` under ``AppConfig.data_dir``, one dedicated
    ``httpx.AsyncClient`` for HLS/segment fetching (independent of
    whatever client FASE 21c ends up giving the Twitch/Kick adapters —
    those aren't wired yet), and ffmpeg resolved from ``PATH``
    (``FFmpegProcessor``'s own default).

    ``segment_manager.progress`` is passed straight through as the
    ``DownloadService`` it returns, rather than a second
    ``ProgressTracker()`` — so ``download_service.progress_of()``
    actually reflects what ``SegmentManager`` records, unlike the two
    independent trackers tests/test_playlist_download_integration.py and
    tests/test_scheduling_integration.py each construct (harmless there,
    since neither asserts on ``progress_of()``).

    No ``EventBus`` yet: nothing in Container consumes
    ``DownloadFinished`` this sub-phase (see docs/architecture-decisions.md
    AD-31/AD-36 — wire it when a real consumer needs it, not before).
    """
    http_client = httpx.AsyncClient()
    hls_reader = HlsPlaylistReader(http_client)
    progress = ProgressTracker()
    segment_manager = SegmentManager(
        fetcher=HttpxSegmentFetcher(http_client),
        retry_policy=RetryPolicy(),
        progress=progress,
    )
    media_processor = MediaProcessor(ffmpeg=FFmpegProcessor(runner=AsyncioProcessRunner()))
    work_dir = config.data_dir / "downloads" / "work"

    executor = DownloadExecutor(
        registry=registry,
        downloads=downloads,
        hls_reader=hls_reader,
        segment_manager=segment_manager,
        media_processor=media_processor,
        work_dir=work_dir,
    )
    queue = DownloadQueue()
    control = JobControlStore()
    coordinator = DownloadCoordinator(
        queue,
        executor,
        worker_count=_DOWNLOAD_WORKER_COUNT,
        is_cancelled=control.is_cancelled,
        is_paused=control.is_paused,
    )
    return DownloadService(
        downloads=downloads,
        progress=progress,
        queue=queue,
        coordinator=coordinator,
        control=control,
    )
