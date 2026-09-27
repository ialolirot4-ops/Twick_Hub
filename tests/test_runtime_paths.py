"""FASE 19: proves ``package_root()`` resolves correctly in both branches
without needing an actual frozen build to test against — the frozen
branch is exercised by monkeypatching ``sys._MEIPASS``, exactly as
PyInstaller sets it at runtime.
"""

from __future__ import annotations

from twick_hub.bootstrap.runtime_paths import package_root


def test_package_root_source_run_points_at_real_twick_hub_directory():
    root = package_root()

    assert root.is_dir()
    assert root.name == "twick_hub"
    assert (root / "presentation" / "qml" / "Main.qml").is_file()


def test_package_root_frozen_run_uses_meipass(monkeypatch, tmp_path):
    fake_bundle_root = tmp_path / "_internal"
    fake_bundle_root.mkdir()
    monkeypatch.setattr("sys._MEIPASS", str(fake_bundle_root), raising=False)

    root = package_root()

    assert root == fake_bundle_root / "twick_hub"
