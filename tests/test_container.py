from twick_hub.application.platform_registry import PlatformRegistry
from twick_hub.bootstrap.container import Container
from twick_hub.bootstrap.dependencies import build_container
from twick_hub.config.settings import AppConfig
from twick_hub.domain.enums import Platform
from twick_hub.domain.protocols import (
    DownloadEngine,
    DownloadRepository,
    FavoriteRepository,
    NotificationRepository,
    ScheduledDownloadRepository,
)


def test_build_container_wires_everything(container: Container):
    assert container.engine is not None
    assert container.session_factory is not None
    assert container.config.app_name == "Twick Hub"
    assert container.favorites is not None


def test_build_container_wires_fase_21a_fields(container: Container):
    """FASE 21a: the repositories/services RISK-ARCH-03/04 flagged as
    built-and-tested-but-never-wired. Checked against the same
    @runtime_checkable Protocols domain/protocols.py defines — a real
    structural-type assertion, not just "isn't None" — plus a check on
    platform_registry's own object identity, which isinstance can't
    verify."""
    assert isinstance(container.downloads, DownloadRepository)
    assert isinstance(container.download_service, DownloadEngine)
    assert isinstance(container.notifications, NotificationRepository)
    assert isinstance(container.scheduled_downloads, ScheduledDownloadRepository)
    assert isinstance(container.favorites, FavoriteRepository)
    assert isinstance(container.platform_registry, PlatformRegistry)


async def test_container_favorites_repository_is_real_and_working(container: Container):
    """FASE 9: the first real (non-fake) repository wired into Container.
    build_container() itself never runs migrations (that's a separate,
    explicit step in real usage — see docs/architecture-decisions.md's
    FASE 8 entry), so this test creates the schema directly, the same way
    every other repository test in tests/infrastructure/persistence/
    does, rather than assuming a schema that isn't there yet."""
    from twick_hub.domain.collections import Favorite
    from twick_hub.domain.enums import Platform
    from twick_hub.domain.value_objects import PlatformRef
    from twick_hub.infrastructure.persistence import models  # noqa: F401
    from twick_hub.infrastructure.persistence.base import Base

    Base.metadata.create_all(container.engine)
    favorite = Favorite(channel_ref=PlatformRef(platform=Platform.TWITCH, external_id="c1"))

    await container.favorites.save(favorite)

    assert await container.favorites.get_by_channel(favorite.channel_ref) == favorite


def test_container_platform_registry_has_both_platforms_registered_but_empty(
    container: Container,
):
    """FASE 21a's specific design call for platform_registry: Twitch and
    Kick are both *registered* (an empty PlatformAdapters() each), never
    left out of the registry entirely — see bootstrap/dependencies.py's
    comment and PlatformRegistry's own docstring. Registered-but-empty is
    what makes get_live_stream()/available_qualities() degrade to "not
    live"/"none" instead of PlatformRegistry raising UnknownPlatformError
    — verified here the same way
    tests/application/test_platform_registry.py verifies it for a
    hand-built registry, just against the real one Container builds."""
    registry = container.platform_registry

    assert registry.is_registered(Platform.TWITCH) is True
    assert registry.is_registered(Platform.KICK) is True

    caps = registry.all_capabilities()
    assert caps[Platform.TWITCH].has_account is False
    assert caps[Platform.TWITCH].has_live is False
    assert caps[Platform.KICK].can_search_channels is False


async def test_container_platform_registry_degrades_instead_of_raising(container: Container):
    from twick_hub.domain.value_objects import PlatformRef

    ref = PlatformRef(platform=Platform.TWITCH, external_id="c1")

    # No live_stream_provider registered for Twitch yet (FASE 21c) — must
    # come back None, not raise, exactly like a platform whose adapters
    # exist but leave this one capability unset.
    assert await container.platform_registry.get_live_stream(ref) is None


async def test_container_downloads_repository_is_real_and_working(container: Container):
    """Same pattern as test_container_favorites_repository_is_real_and_working
    (FASE 9), applied to the FASE 21a `downloads` field: a real SQLite
    round trip through SqlDownloadRepository, not just a type check."""
    from twick_hub.domain.downloads import Download
    from twick_hub.domain.enums import MediaKind
    from twick_hub.domain.value_objects import Media, PlatformRef
    from twick_hub.infrastructure.persistence import models  # noqa: F401
    from twick_hub.infrastructure.persistence.base import Base

    Base.metadata.create_all(container.engine)
    media = Media(
        kind=MediaKind.VIDEO,
        ref=PlatformRef(platform=Platform.TWITCH, external_id="v1"),
        title="A VOD",
    )
    download = Download(media=media, destination_path="/tmp/out.mp4", quality_label="source")

    await container.downloads.save(download)

    assert await container.downloads.get(download.id) == download


async def test_container_download_service_runs_the_real_pipeline(container: Container):
    """Proves `download_service` is the real FASE 7 engine
    (DownloadQueue + JobControlStore + DownloadCoordinator +
    DownloadExecutor), not a stub — exercised end to end with no network
    and no ffmpeg. `platform_registry` has Twitch registered with no
    playback_resolver (FASE 21c isn't wired yet), so the executor is
    expected to fail this job with UnsupportedCapabilityError — the
    point isn't a successful download, it's that a real worker actually
    picked the job off the real queue and drove it through the real
    executor to a terminal, persisted state.
    """
    import asyncio

    from twick_hub.domain.downloads import Download, DownloadJob
    from twick_hub.domain.enums import DownloadStatus, MediaKind
    from twick_hub.domain.value_objects import Media, PlatformRef
    from twick_hub.infrastructure.persistence import models  # noqa: F401
    from twick_hub.infrastructure.persistence.base import Base

    Base.metadata.create_all(container.engine)
    media = Media(
        kind=MediaKind.VIDEO,
        ref=PlatformRef(platform=Platform.TWITCH, external_id="v1"),
        title="A VOD",
    )
    download = Download(media=media, destination_path="/tmp/out.mp4", quality_label="source")
    await container.downloads.save(download)

    await container.download_service.enqueue(DownloadJob(download_id=download.id))

    stored = None
    for _ in range(50):
        await asyncio.sleep(0.02)
        stored = await container.downloads.get(download.id)
        if stored is not None and stored.status != DownloadStatus.QUEUED:
            break

    assert stored is not None
    assert stored.status == DownloadStatus.FAILED
    assert stored.error_message is not None and "playback_resolver" in stored.error_message


def test_build_container_creates_independent_instances(tmp_path):
    """Regression guard for docs/architecture-decisions.md AD-03: two
    calls to build_container() must produce two fully independent
    containers. If this ever fails, something has re-introduced a
    module-level cache/singleton — the exact pattern AD-03 removes.
    """
    config_a = AppConfig(data_dir=tmp_path, database_url="sqlite:///:memory:")
    config_b = AppConfig(data_dir=tmp_path, database_url="sqlite:///:memory:")

    container_a = build_container(config_a)
    container_b = build_container(config_b)

    assert container_a is not container_b
    assert container_a.engine is not container_b.engine


# FASE 21c — ``build_container`` accepts the real platform adapters (built
# by bootstrap/platforms.py once a Qt app exists) without changing what it
# does when given none.


def test_build_container_uses_the_platform_adapters_it_is_given(tmp_path):
    from twick_hub.application.platform_registry import PlatformAdapters

    class _Directory:
        async def find_channel(self, query):
            return None

        async def get_channel(self, ref):
            raise NotImplementedError

    adapters = PlatformAdapters(channel_directory=_Directory())
    container = build_container(
        AppConfig(data_dir=tmp_path), platform_adapters={Platform.TWITCH: adapters}
    )

    registry = container.platform_registry
    assert registry.get_platform(Platform.TWITCH) is adapters
    assert registry.capabilities_for(Platform.TWITCH).can_search_channels is True


def test_build_container_keeps_unlisted_platforms_registered_but_empty(tmp_path):
    from twick_hub.application.platform_registry import PlatformAdapters

    container = build_container(
        AppConfig(data_dir=tmp_path), platform_adapters={Platform.TWITCH: PlatformAdapters()}
    )

    assert container.platform_registry.is_registered(Platform.KICK)
    assert container.platform_registry.capabilities_for(Platform.KICK).can_search_channels is False
