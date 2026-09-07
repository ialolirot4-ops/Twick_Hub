from twitchlink_next.config.settings import AppConfig


def test_defaults_are_safe_with_zero_configuration(tmp_path):
    config = AppConfig(data_dir=tmp_path)
    assert config.app_name == "TwitchLink Next"
    assert config.resolved_database_url().startswith("sqlite:///")


def test_explicit_database_url_wins_over_default(tmp_path):
    config = AppConfig(data_dir=tmp_path, database_url="sqlite:///:memory:")
    assert config.resolved_database_url() == "sqlite:///:memory:"


def test_resolved_database_url_creates_data_dir(tmp_path):
    target = tmp_path / "nested" / "dir"
    config = AppConfig(data_dir=target)
    config.resolved_database_url()
    assert target.is_dir()
