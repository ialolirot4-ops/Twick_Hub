from __future__ import annotations

import pytest

from twick_hub.domain.enums import Theme
from twick_hub.domain.settings import SETTINGS_ID, Settings


def test_defaults_are_a_valid_settings_object():
    settings = Settings()
    assert settings.id == SETTINGS_ID
    assert settings.language == "en"
    assert settings.theme is Theme.SYSTEM
    assert settings.max_concurrent_downloads == 3
    assert settings.live_monitor_poll_interval_seconds is None


def test_updated_returns_a_new_instance_and_leaves_the_original_alone():
    settings = Settings()

    updated = settings.updated(theme=Theme.DARK, language="es")

    assert settings.theme is Theme.SYSTEM  # original untouched
    assert updated.theme is Theme.DARK
    assert updated.language == "es"
    assert updated.id == settings.id


def test_reset_to_defaults_clears_every_change_but_keeps_the_id():
    settings = Settings(id="custom-id").updated(
        theme=Theme.DARK, language="es", max_concurrent_downloads=10
    )

    reset = settings.reset_to_defaults()

    assert reset == Settings(id="custom-id")
    assert reset.theme is Theme.SYSTEM
    assert reset.max_concurrent_downloads == 3


@pytest.mark.parametrize(
    "fields",
    [
        {"language": ""},
        {"language": "   "},
        {"default_quality_preference": ""},
        {"max_concurrent_downloads": 0},
        {"max_concurrent_downloads": -1},
        {"retry_max_attempts": 0},
        {"retry_base_delay_seconds": -1},
        {"retry_max_delay_seconds": 0.5, "retry_base_delay_seconds": 1.0},
        {"live_monitor_poll_interval_seconds": 0},
        {"live_monitor_poll_interval_seconds": -5},
    ],
)
def test_invalid_fields_are_rejected(fields):
    with pytest.raises(ValueError):
        Settings(**fields)


def test_a_none_live_monitor_poll_interval_is_valid_and_means_use_the_default():
    assert (
        Settings(live_monitor_poll_interval_seconds=None).live_monitor_poll_interval_seconds is None
    )


def test_retry_max_delay_equal_to_base_is_valid():
    Settings(retry_base_delay_seconds=5.0, retry_max_delay_seconds=5.0)  # must not raise


def test_optional_string_fields_default_to_none():
    settings = Settings()
    assert settings.default_directory is None
    assert settings.default_format is None
    assert settings.temp_directory is None
