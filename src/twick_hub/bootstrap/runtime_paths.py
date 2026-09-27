"""Resolves where the ``twick_hub`` package's on-disk data (QML files,
today; potentially bundled resources like FFmpeg later — see
docs/architecture-decisions.md, FASE 19) actually lives, whether the app
is running from source or from a PyInstaller-frozen build.

Why this exists (FASE 19): every prior use of package-relative data
(``bootstrap/application.py``'s ``_QML_MAIN``) computed the path via
``Path(__file__).resolve().parents[N]``. That works for a normal
source/editable-install run, but breaks under PyInstaller: a frozen
module's ``__file__`` points at a synthetic location inside the bundled
archive (e.g. ``.../_internal/base_library.zip/twick_hub/...``), which
does not exist as a real directory on disk, so sibling-relative
navigation from it does not find files that PyInstaller actually
extracted elsewhere. PyInstaller instead exposes the real on-disk root
of the frozen bundle's collected data as ``sys._MEIPASS`` (set for both
``--onedir`` and ``--onefile`` builds). ``packaging/pyinstaller/twick_hub.spec``
places the ``twick_hub`` package's data under a ``twick_hub/`` folder
inside that root, mirroring the source layout, so the two branches below
resolve to the same relative structure either way.
"""

from __future__ import annotations

import sys
from pathlib import Path


def package_root() -> Path:
    """Directory that contains ``twick_hub``'s package data on disk.

    Frozen (PyInstaller, ``sys._MEIPASS`` set): ``<bundle_root>/twick_hub``.
    Source / editable install: the real ``src/twick_hub`` directory next
    to this module (``parents[1]`` from ``bootstrap/runtime_paths.py``).
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass is not None:
        return Path(meipass) / "twick_hub"
    return Path(__file__).resolve().parents[1]
