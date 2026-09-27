"""Settings use cases (Master Plan §50, FASE 13).

Deliberately three thin use cases, not one per field: ``Settings`` is
edited as a whole value (the same "always a complete, valid object"
pattern ``Favorite``/``ScheduledDownload`` already use), so the caller —
the Settings page view-model — reads the current ``Settings``, builds the
next one with ``.updated(**changed_fields)``, and saves it. A per-field
use case for every one of §50's ten-plus knobs would be a lot of
near-identical code for no real benefit; ``Settings.__post_init__``
already validates the whole object no matter which use case saved it.
"""

from __future__ import annotations

from dataclasses import dataclass

from twick_hub.domain.protocols import SettingsRepository
from twick_hub.domain.settings import Settings


@dataclass(frozen=True, slots=True)
class GetSettingsUseCase:
    settings: SettingsRepository

    async def execute(self) -> Settings:
        return await self.settings.get()


@dataclass(frozen=True, slots=True)
class UpdateSettingsUseCase:
    settings: SettingsRepository

    async def execute(self, updated: Settings) -> Settings:
        """Takes the *complete* next ``Settings`` — validated by its own
        constructor before this is ever called, so this use case has
        nothing left to check. Callers build ``updated`` from the current
        settings via ``.updated(theme=Theme.DARK)`` rather than
        constructing one from scratch, so fields they didn't mean to
        touch aren't silently reset to defaults."""
        await self.settings.save(updated)
        return updated


@dataclass(frozen=True, slots=True)
class ResetSettingsUseCase:
    settings: SettingsRepository

    async def execute(self) -> Settings:
        """The Settings page mock's "Reset to defaults" action."""
        current = await self.settings.get()
        defaults = current.reset_to_defaults()
        await self.settings.save(defaults)
        return defaults
