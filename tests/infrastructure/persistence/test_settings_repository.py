from __future__ import annotations

from sqlalchemy.orm import sessionmaker

from twick_hub.domain.enums import Theme
from twick_hub.domain.settings import SETTINGS_ID, Settings
from twick_hub.infrastructure.persistence.settings_repository import SqlSettingsRepository


async def test_get_on_a_fresh_database_returns_defaults_without_writing_a_row(
    session_factory: sessionmaker,
):
    repo = SqlSettingsRepository(session_factory)

    settings = await repo.get()

    assert settings == Settings()
    with session_factory() as session:
        from twick_hub.infrastructure.persistence.models import SettingsRow

        assert session.get(SettingsRow, SETTINGS_ID) is None  # get() alone never persists


async def test_save_then_get_round_trips_every_field(session_factory: sessionmaker):
    repo = SqlSettingsRepository(session_factory)
    settings = Settings(
        language="es-MX",
        minimize_to_tray=True,
        default_directory="D:/downloads",
        default_quality_preference="720p",
        default_format="mkv",
        max_concurrent_downloads=7,
        retry_max_attempts=5,
        retry_base_delay_seconds=2.5,
        retry_max_delay_seconds=60.0,
        notifications_enabled=False,
        theme=Theme.DARK,
        temp_directory="D:/tmp",
        live_monitor_poll_interval_seconds=45.0,
    )

    await repo.save(settings)
    fetched = await repo.get()

    assert fetched == settings


async def test_saving_twice_updates_the_same_row_not_a_second_one(session_factory: sessionmaker):
    repo = SqlSettingsRepository(session_factory)
    await repo.save(Settings(language="es"))
    await repo.save(Settings(language="fr"))

    fetched = await repo.get()

    assert fetched.language == "fr"
    with session_factory() as session:
        from sqlalchemy import func, select

        from twick_hub.infrastructure.persistence.models import SettingsRow

        count = session.execute(select(func.count()).select_from(SettingsRow)).scalar_one()
    assert count == 1


async def test_optional_none_fields_round_trip_as_none(session_factory: sessionmaker):
    repo = SqlSettingsRepository(session_factory)
    await repo.save(Settings())

    fetched = await repo.get()

    assert fetched.default_directory is None
    assert fetched.default_format is None
    assert fetched.temp_directory is None
    assert fetched.live_monitor_poll_interval_seconds is None
