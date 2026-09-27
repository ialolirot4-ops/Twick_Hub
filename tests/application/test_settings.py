from __future__ import annotations

from tests.application.fakes import InMemorySettingsRepository
from twick_hub.application.settings import (
    GetSettingsUseCase,
    ResetSettingsUseCase,
    UpdateSettingsUseCase,
)
from twick_hub.domain.enums import Theme
from twick_hub.domain.settings import Settings


async def test_get_settings_returns_defaults_on_a_fresh_install():
    repo = InMemorySettingsRepository()

    settings = await GetSettingsUseCase(settings=repo).execute()

    assert settings == Settings()


async def test_update_settings_persists_the_new_value():
    repo = InMemorySettingsRepository()
    current = await GetSettingsUseCase(settings=repo).execute()
    changed = current.updated(theme=Theme.DARK, max_concurrent_downloads=5)

    result = await UpdateSettingsUseCase(settings=repo).execute(changed)

    assert result == changed
    stored = await repo.get()
    assert stored.theme is Theme.DARK
    assert stored.max_concurrent_downloads == 5


async def test_update_settings_is_a_full_replace_not_a_merge_of_unspecified_fields():
    """Building the next Settings from .updated() (not from scratch) is
    the caller's job — this test documents why: a bare ``Settings(...)``
    passed to the use case resets everything else to defaults too."""
    repo = InMemorySettingsRepository()
    await UpdateSettingsUseCase(settings=repo).execute(Settings().updated(language="es"))

    await UpdateSettingsUseCase(settings=repo).execute(Settings(theme=Theme.DARK))  # from scratch

    stored = await repo.get()
    assert stored.language == "en"  # reset to default, not "es"
    assert stored.theme is Theme.DARK


async def test_reset_settings_restores_defaults_and_persists_them():
    repo = InMemorySettingsRepository()
    changed = Settings().updated(theme=Theme.LIGHT, language="fr")
    await UpdateSettingsUseCase(settings=repo).execute(changed)

    result = await ResetSettingsUseCase(settings=repo).execute()

    assert result == Settings()
    stored = await repo.get()
    assert stored == Settings()


async def test_reset_settings_on_a_fresh_install_is_a_noop_that_still_saves_defaults():
    repo = InMemorySettingsRepository()

    result = await ResetSettingsUseCase(settings=repo).execute()

    assert result == Settings()
