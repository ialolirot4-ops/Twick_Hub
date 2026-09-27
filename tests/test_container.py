from twick_hub.bootstrap.container import Container
from twick_hub.bootstrap.dependencies import build_container
from twick_hub.config.settings import AppConfig


def test_build_container_wires_everything(container: Container):
    assert container.engine is not None
    assert container.session_factory is not None
    assert container.config.app_name == "Twick Hub"
    assert container.favorites is not None


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
