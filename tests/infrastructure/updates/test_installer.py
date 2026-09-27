from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from twick_hub.infrastructure.updates.installer import DirectoryBackupInstaller, InstallError


def _make_zip(path: Path, files: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return path


def _installer(tmp_path: Path) -> tuple[DirectoryBackupInstaller, Path, Path]:
    app_dir = tmp_path / "app"
    backup_dir = tmp_path / "backup"
    return DirectoryBackupInstaller(app_dir, backup_dir), app_dir, backup_dir


async def test_installs_a_fresh_app_directory(tmp_path: Path):
    installer, app_dir, _ = _installer(tmp_path)
    artifact = _make_zip(tmp_path / "u.zip", {"app.exe": b"v2", "data/config.json": b"{}"})

    await installer.install(str(artifact))

    assert (app_dir / "app.exe").read_bytes() == b"v2"
    assert (app_dir / "data" / "config.json").read_bytes() == b"{}"


async def test_backs_up_the_previous_version_before_replacing(tmp_path: Path):
    installer, app_dir, backup_dir = _installer(tmp_path)
    app_dir.mkdir(parents=True)
    (app_dir / "app.exe").write_bytes(b"v1")
    artifact = _make_zip(tmp_path / "u.zip", {"app.exe": b"v2"})

    await installer.install(str(artifact))

    assert (backup_dir / "app.exe").read_bytes() == b"v1"
    assert (app_dir / "app.exe").read_bytes() == b"v2"


async def test_rollback_restores_the_backed_up_version(tmp_path: Path):
    installer, app_dir, _ = _installer(tmp_path)
    app_dir.mkdir(parents=True)
    (app_dir / "app.exe").write_bytes(b"v1")
    artifact = _make_zip(tmp_path / "u.zip", {"app.exe": b"v2"})
    await installer.install(str(artifact))

    await installer.rollback()

    assert (app_dir / "app.exe").read_bytes() == b"v1"


async def test_rollback_without_a_prior_install_raises():
    installer = DirectoryBackupInstaller(Path("/nonexistent/app"), Path("/nonexistent/backup"))
    with pytest.raises(InstallError, match="no backup"):
        await installer.rollback()


async def test_a_corrupt_archive_auto_rolls_back_and_raises(tmp_path: Path):
    installer, app_dir, _ = _installer(tmp_path)
    app_dir.mkdir(parents=True)
    (app_dir / "app.exe").write_bytes(b"v1")
    bad_artifact = tmp_path / "bad.zip"
    bad_artifact.write_bytes(b"not a real zip file")

    with pytest.raises(InstallError):
        await installer.install(str(bad_artifact))

    assert (app_dir / "app.exe").read_bytes() == b"v1"  # rolled back automatically


async def test_a_path_traversal_entry_is_rejected_before_extracting_anything(tmp_path: Path):
    installer, app_dir, _ = _installer(tmp_path)
    app_dir.mkdir(parents=True)
    (app_dir / "app.exe").write_bytes(b"v1")
    malicious = _make_zip(tmp_path / "evil.zip", {"../../etc/passwd": b"pwned", "app.exe": b"v2"})

    with pytest.raises(InstallError, match="escapes"):
        await installer.install(str(malicious))

    # rolled back: the original file is untouched, and nothing escaped
    assert (app_dir / "app.exe").read_bytes() == b"v1"
    assert not (tmp_path / "etc").exists()


async def test_an_absolute_path_entry_is_rejected(tmp_path: Path):
    installer, app_dir, _ = _installer(tmp_path)
    malicious = _make_zip(tmp_path / "evil.zip", {"/etc/passwd": b"pwned"})

    with pytest.raises(InstallError, match="escapes"):
        await installer.install(str(malicious))


async def test_a_failed_first_ever_install_with_no_prior_backup_just_clears_the_partial_extraction(
    tmp_path: Path,
):
    """No app_dir existed before this install, so there is nothing to
    "roll back" to — install()'s own failure handling must not confuse
    that with an error (unlike the public rollback(), which is meant for
    an explicit "undo a completed install" and correctly requires one)."""
    installer, app_dir, backup_dir = _installer(tmp_path)
    malicious = _make_zip(tmp_path / "evil.zip", {"../escape.txt": b"x", "app.exe": b"v1"})

    with pytest.raises(InstallError, match="escapes"):
        await installer.install(str(malicious))

    assert not app_dir.exists()
    assert not backup_dir.exists()


async def test_second_install_replaces_the_previous_backup_not_accumulates(tmp_path: Path):
    installer, app_dir, backup_dir = _installer(tmp_path)
    app_dir.mkdir(parents=True)
    (app_dir / "app.exe").write_bytes(b"v1")
    await installer.install(str(_make_zip(tmp_path / "u2.zip", {"app.exe": b"v2"})))

    await installer.install(str(_make_zip(tmp_path / "u3.zip", {"app.exe": b"v3"})))

    assert (backup_dir / "app.exe").read_bytes() == b"v2"  # backup is now v2, not v1
    assert (app_dir / "app.exe").read_bytes() == b"v3"


async def test_a_failure_partway_through_extraction_with_no_backup_clears_the_partial_files(
    tmp_path: Path,
):
    """Distinct from
    test_a_failed_first_ever_install_with_no_prior_backup_just_clears_the_partial_extraction
    above, where the path-traversal check rejects the archive *before*
    extracting a single byte, so ``app_dir`` never even gets created.
    Here extraction genuinely starts and writes a real file, and only
    then does a later entry in the same archive fail — the only path
    that reaches ``_restore_or_clear``'s own ``elif app_directory.exists()``
    branch rather than either its ``if`` branch (a backup did exist) or
    the do-nothing case (nothing was ever written)."""
    installer, app_dir, backup_dir = _installer(tmp_path)
    artifact_path = tmp_path / "u.zip"
    _make_zip(artifact_path, {"good.txt": b"fine", "bad.txt": b"will-be-corrupted"})
    # Flip a byte inside the second (STORED, uncompressed) entry's own data
    # so its CRC-32 no longer matches -- the zip's central directory and
    # overall structure stay intact, but extracting *that one entry*
    # fails, after "good.txt" has already been written to disk.
    raw = bytearray(artifact_path.read_bytes())
    marker = b"will-be-corrupted"
    index = raw.index(marker)
    raw[index] ^= 0xFF
    artifact_path.write_bytes(bytes(raw))

    with pytest.raises(InstallError):
        await installer.install(str(artifact_path))

    assert not app_dir.exists()
    assert not backup_dir.exists()
