"""The default, packaging-agnostic ``UpdateInstaller`` — a full backup of
the app directory before replacing it, restoring that backup on any
install failure or explicit ``rollback()`` call.

Master Plan §51 lists FASE 19 ("packaging strategy") as a prerequisite
this phase doesn't actually have yet (docs/architecture-decisions.md's
FASE 14 entry): there is no decided installer technology (MSI, an
AppImage, a signed macOS bundle, ...) to build against. This is a
deliberately conservative fallback that works for *any* packaging that
ships as "a directory of files" — extract a new build's files over the
old ones, keep the old ones safe until the new ones are confirmed good.
An OS-specific installer, once FASE 19 decides on one, replaces this
without any change to ``UpdateService`` or the ``UpdateInstaller``
protocol it depends on.
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path


class InstallError(Exception):
    pass


class DirectoryBackupInstaller:
    def __init__(self, app_directory: Path, backup_directory: Path) -> None:
        self._app_directory = app_directory
        self._backup_directory = backup_directory

    async def install(self, artifact_path: str) -> None:
        """Backs up ``app_directory``, then extracts ``artifact_path`` (a
        zip archive) over it. Restores the backup automatically if
        anything about the extraction itself fails, so a partial,
        half-updated app directory is never left behind."""
        self._backup_directory.parent.mkdir(parents=True, exist_ok=True)
        if self._backup_directory.exists():
            shutil.rmtree(self._backup_directory)
        if self._app_directory.exists():
            shutil.copytree(self._app_directory, self._backup_directory)

        try:
            with zipfile.ZipFile(artifact_path) as archive:
                _check_no_path_traversal(archive, self._app_directory)
                archive.extractall(self._app_directory)
        except Exception as exc:
            self._restore_or_clear()
            raise InstallError(f"install failed, rolled back: {exc}") from exc

    async def rollback(self) -> None:
        if not self._backup_directory.exists():
            raise InstallError("no backup available to roll back to")
        if self._app_directory.exists():
            shutil.rmtree(self._app_directory)
        shutil.copytree(self._backup_directory, self._app_directory)

    def _restore_or_clear(self) -> None:
        """Used only by ``install()``'s own failure handling — unlike the
        public ``rollback()``, "there is no backup" is not an error here:
        it simply means there was nothing to back up (a first-ever
        install into an empty directory), so the correct recovery is to
        remove whatever the failed extraction partially wrote, leaving
        the app directory exactly as absent as it started."""
        if self._backup_directory.exists():
            if self._app_directory.exists():
                shutil.rmtree(self._app_directory)
            shutil.copytree(self._backup_directory, self._app_directory)
        elif self._app_directory.exists():
            shutil.rmtree(self._app_directory)


def _check_no_path_traversal(archive: zipfile.ZipFile, target: Path) -> None:
    """A malicious or corrupt artifact must not be able to write outside
    ``target`` via ``../`` entries or an absolute path — checked before a
    single byte is extracted, not cleaned up after."""
    resolved_target = target.resolve()
    for name in archive.namelist():
        destination = (target / name).resolve()
        if resolved_target not in destination.parents and destination != resolved_target:
            raise InstallError(f"artifact entry escapes the install directory: {name!r}")
