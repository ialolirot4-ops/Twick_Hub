from twick_hub.bootstrap.container import Container
from twick_hub.bootstrap.dependencies import build_container
from twick_hub.config.settings import AppConfig


def test_build_container_wires_everything(container: Container):
    assert container.engine is not None
    assert container.session_factory is not None
    assert container.config.app_name == "Twick Hub"


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
