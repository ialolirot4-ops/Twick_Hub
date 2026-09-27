"""Locates and backs up a TwitchLink 3.5.x ``settings.json`` — Master Plan
§52 (FASE 15)'s "detect" and "backup" steps.

Path convention mirrors ``Core/Config.py`` in the legacy repository
exactly: ``APPDATA_FILE = APPDATA_PATH / "settings.json"``, where
``APPDATA_PATH = OSUtils.getSystemAppDataPath() / Meta.APP_NAME`` and
``Meta.APP_NAME == "TwitchLink"``. This project's own
``config/settings.py``'s ``default_data_dir()`` already resolves the same
per-OS base directory for Twick Hub's *own* data — this module applies
that identical convention to the legacy app's name instead, rather than
inventing a second way to find a per-OS app-data folder.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_LEGACY_APP_NAME = "TwitchLink"
_LEGACY_SETTINGS_FILENAME = "settings.json"


def default_legacy_settings_path() -> Path | None:
    """Where TwitchLink 3.5.x would have written its ``settings.json``.

    Returns ``None`` on a platform TwitchLink 3.5.x never shipped an
    ``OSAdapter`` for. Confirmed in this phase's audit of the legacy
    repository: ``Services/Utils/OSAdapters/`` contains only
    ``Windows.py`` and ``MacOS.py`` (``OSUtils = WindowsUtils if
    BaseAdapter.isWindows() else MacOSUtils`` — there is no Linux branch
    at all). A real 3.5.x install could not have existed on Linux with
    any path this function could name, so detection reports "not
    applicable" there rather than guessing an unofficial location.
    """
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        if not base:
            return None
        appdata = Path(base)
    elif sys.platform == "darwin":
        appdata = Path.home() / "Library" / "Application Support"
    else:
        return None
    return appdata / _LEGACY_APP_NAME / _LEGACY_SETTINGS_FILENAME


@dataclass(frozen=True, slots=True)
class DetectionResult:
    found: bool
    path: Path | None
    reason: str | None = None  # populated when found is False


def detect(candidate_path: Path | None = None) -> DetectionResult:
    """FASE 15's "detect" step. ``candidate_path`` overrides the default
    per-OS location — a caller pointing at a specific file (a future "browse
    for my old install" UI action, or a test) — detect() never searches
    beyond the one path it's given or the one default it knows; guessing
    at other locations isn't this module's job.
    """
    path = candidate_path if candidate_path is not None else default_legacy_settings_path()
    if path is None:
        return DetectionResult(
            found=False,
            path=None,
            reason=(
                f"TwitchLink 3.5.x shipped no OSAdapter for this platform "
                f"({sys.platform!r}) — it has no known settings path here."
            ),
        )
    if not path.is_file():
        return DetectionResult(found=False, path=path, reason=f"no file at {path}")
    return DetectionResult(found=True, path=path)


def backup(source: Path, backup_dir: Path, *, now: datetime | None = None) -> Path:
    """FASE 15's "backup" step. Copies ``source`` byte-for-byte into
    ``backup_dir`` under a timestamped name and returns the backup's path.

    Never touches, moves, or opens ``source`` for writing — only ever
    reads from it (Master Plan permanent rule #15, "No romper datos del
    usuario": whatever TwitchLink left on disk must still be exactly
    there afterwards, migration outcome notwithstanding). Safe to call
    repeatedly — every call gets its own timestamped file rather than
    overwriting a previous backup, so an earlier backup from a previous
    run is never lost.

    Raises ``OSError`` if the copy doesn't come out the same size as the
    source — better to fail loudly here than hand a truncated "backup"
    to a caller that will trust it as the reversibility net.
    """
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = (now or datetime.now()).strftime("%Y%m%dT%H%M%S%f")
    destination = backup_dir / f"{source.stem}.{timestamp}{source.suffix}.bak"
    shutil.copy2(source, destination)
    source_size = source.stat().st_size
    backup_size = destination.stat().st_size
    if backup_size != source_size:
        raise OSError(
            f"legacy settings backup size mismatch: source={source_size} bytes, "
            f"backup={backup_size} bytes at {destination}"
        )
    return destination
