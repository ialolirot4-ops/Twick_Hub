"""Checks whether a newer version is available (Master Plan §51:
"Verificar: origen; ... versiones").

Origin verification already happened by the time ``UpdateSource.check()``
returns an ``UpdateInfo`` (see domain/updates.py's module docstring) —
this class's own job is strictly the version comparison: a manifest that
verifies perfectly but describes a version that isn't actually newer than
what's installed is not an "update" and must not be reported as one
(this is what stops a replayed old-but-validly-signed manifest from being
treated as new).
"""

from __future__ import annotations

from dataclasses import dataclass

from twick_hub.domain.protocols import UpdateSource
from twick_hub.domain.updates import UpdateInfo
from twick_hub.domain.version import Version


@dataclass(frozen=True, slots=True)
class UpdateCheckResult:
    update: UpdateInfo | None  # None: already up to date, or nothing published
    current_version: Version


class UpdateChecker:
    def __init__(self, source: UpdateSource, current_version: Version) -> None:
        self._source = source
        self.current_version = current_version

    async def check(self) -> UpdateCheckResult:
        info = await self._source.check()
        if info is None or info.version <= self.current_version:
            return UpdateCheckResult(update=None, current_version=self.current_version)
        return UpdateCheckResult(update=info, current_version=self.current_version)
