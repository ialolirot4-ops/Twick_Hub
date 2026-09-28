"""The dependency container.

A plain, explicit data holder — not a service locator. Nothing in this
codebase does ``Container.instance().thing`` or reaches a dependency
through import-time global state. A ``Container`` is built exactly once
(``bootstrap/dependencies.py``) and passed by constructor to whatever
needs it.

This replaces TwitchLink 3.5.5's ``Core/App.py``, which creates
``Instance = App(...)`` — plus eight services hung off it
(``NetworkAccessManager``, ``TwitchGQL``, ``Translator``,
``NotificationManager``, ``ContentManager``, ``TempManager``,
``ImageLoader``, ``PartnerContentManager``) — as a side effect of
importing the module. See docs/architecture-decisions.md AD-03 and
docs/migration-map.md.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from twick_hub.application.platform_registry import PlatformRegistry
from twick_hub.config.settings import AppConfig
from twick_hub.domain.protocols import (
    DownloadEngine,
    DownloadRepository,
    FavoriteRepository,
    NotificationRepository,
    ScheduledDownloadRepository,
)

# One thing to shut down: an async callable with no arguments, e.g.
# ``DownloadService.stop`` or ``httpx.AsyncClient.aclose``.
Closer = Callable[[], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class Container:
    config: AppConfig
    engine: Engine
    session_factory: sessionmaker
    favorites: FavoriteRepository
    downloads: DownloadRepository
    download_service: DownloadEngine
    notifications: NotificationRepository
    scheduled_downloads: ScheduledDownloadRepository
    platform_registry: PlatformRegistry
    # FASE 22.1 (RISK-ARCH-09, AD-103): what the container opened and must
    # be closed at shutdown, in the order to run them — ``Application``
    # awaits each one inside the app's event loop, before
    # ``engine.dispose()``. The container lists what *it* built (the
    # download workers, then the download engine's HTTP client); whoever
    # builds something else and hands it in (``main()``'s shared platform
    # HTTP client) appends it via ``build_container(extra_closers=...)``.
    closers: tuple[Closer, ...] = ()

    # FASE 21a wires everything above that doesn't need a live Twitch/Kick
    # session — see docs/architecture-decisions.md's FASE 21a entry for
    # the download-engine assembly decisions (worker count, work_dir,
    # HTTP client, ffmpeg path) that FASE 7 (AD-36) deliberately left
    # open. `platform_registry` is built with both platforms registered
    # under an empty `PlatformAdapters()` each, never left unregistered —
    # see PlatformRegistry's own docstring — so callers degrade (no
    # live status, no channel search) instead of raising
    # UnknownPlatformError. Real `AccountProvider`/`ChannelDirectory`
    # adapters for Twitch/Kick are FASE 21c's job, not this one — they
    # need live credentials this environment doesn't have (see
    # docs/risk-register.md RISK-ARCH-01).
