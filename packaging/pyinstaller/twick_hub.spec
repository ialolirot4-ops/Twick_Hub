# -*- mode: python ; coding: utf-8 -*-
"""FASE 19 (Packaging) — PyInstaller spec for Twick Hub.

Produces a ``--onedir`` bundle (a directory of files, not a single
self-extracting exe) — see docs/architecture-decisions.md for why: it
starts faster than ``--onefile`` (no self-extraction step on every
launch) and matches what
``src/twick_hub/infrastructure/updates/installer.py``'s
``DirectoryBackupInstaller`` already assumes the app is distributed as
(a replaceable directory of files), rather than leaving that assumption
unvalidated (docs/risk-register.md RISK-ARCH-07).

Run from the repository root:

    pyinstaller packaging/pyinstaller/twick_hub.spec

See docs/packaging.md for the full build/CI story, known limitations,
and why a real Windows x64 artifact can only be produced by actually
running this on Windows (or via the CI workflow in
``.github/workflows/build-windows.yml``) — PyInstaller does not
cross-compile.
"""

from __future__ import annotations

import sys
from pathlib import Path

block_cipher = None

# SPECPATH is injected by PyInstaller into the spec file's execution
# namespace — the directory containing this .spec file.
_PROJECT_ROOT = Path(SPECPATH).resolve().parents[1]  # noqa: F821
_QML_SRC = _PROJECT_ROOT / "src" / "twick_hub" / "presentation" / "qml"

if not _QML_SRC.is_dir():
    raise SystemExit(f"QML source directory not found: {_QML_SRC}")

# Destination mirrors the source layout under a top-level ``twick_hub``
# folder inside the bundle, matching what
# ``twick_hub.bootstrap.runtime_paths.package_root()`` expects to find
# via ``sys._MEIPASS`` when frozen.
datas = [(str(_QML_SRC), "twick_hub/presentation/qml")]

hiddenimports = [
    # keyring resolves its backend via entry-point discovery at import
    # time; PyInstaller's static analysis does not see that dynamic
    # dispatch, so the concrete backend for the target OS must be
    # listed explicitly. Only the backend for the platform this spec is
    # actually *run on* is added — the real Windows backend is only
    # importable (and only needed) when this spec runs on a Windows
    # build machine/CI runner, not from this Linux dry-run.
    "keyring.backends",
]
if sys.platform == "win32":
    hiddenimports.append("keyring.backends.Windows")
elif sys.platform == "darwin":
    hiddenimports.append("keyring.backends.macOS")
else:
    hiddenimports.append("keyring.backends.SecretService")

a = Analysis(
    [str(Path(SPECPATH) / "entrypoint.py")],  # noqa: F821
    pathex=[str(_PROJECT_ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TwickHub",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="TwickHub",
)
