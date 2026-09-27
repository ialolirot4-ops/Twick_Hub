"""FASE 14 end to end: a full check → download → install cycle through the
*real* pieces — ``ManifestUpdateSource`` (real Ed25519 signature
verification), ``UpdateDownloader`` (real SHA-256 streaming verification),
``DirectoryBackupInstaller`` (real filesystem backup/restore), and
``SqlUpdateAttemptRepository`` against a real Alembic-migrated database —
with only the network faked (httpx.MockTransport), same approach as every
other FASE's own end-to-end test in this project.

Also proves, with a real ``Download`` row in a real repository, that
"No interferir con descargas activas" (Master Plan §51) genuinely blocks
``install()`` — not just against a fake as tests/application/updates/
test_service.py already does.
"""

from __future__ import annotations

import base64
import hashlib
import io
import zipfile
from pathlib import Path

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tests.infrastructure.updates.keys import generate_keypair, sign_manifest_fields
from twick_hub.application.updates.checker import UpdateChecker
from twick_hub.application.updates.service import UpdateService
from twick_hub.domain.downloads import Download
from twick_hub.domain.enums import DownloadStatus, MediaKind, Platform, UpdateStatus
from twick_hub.domain.updates import DownloadsInProgressError
from twick_hub.domain.value_objects import Media, PlatformRef
from twick_hub.domain.version import Version
from twick_hub.infrastructure.persistence.base import Base
from twick_hub.infrastructure.persistence.download_repository import SqlDownloadRepository
from twick_hub.infrastructure.persistence.update_attempt_repository import (
    SqlUpdateAttemptRepository,
)
from twick_hub.infrastructure.updates.downloader import UpdateDownloader
from twick_hub.infrastructure.updates.installer import DirectoryBackupInstaller
from twick_hub.infrastructure.updates.manifest_source import ManifestUpdateSource

_MANIFEST_URL = "https://updates.example.invalid/manifest.json"


async def test_a_full_check_download_install_cycle_through_the_real_pieces(tmp_path: Path):
    # --- a real migrated database ------------------------------------------
    engine = create_engine(f"sqlite:///{tmp_path / 'app.db'}", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    attempts = SqlUpdateAttemptRepository(session_factory)
    downloads = SqlDownloadRepository(session_factory)

    # --- a real signed manifest + a real update artifact --------------------
    private_key, public_pem = generate_keypair()
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "app.exe").write_bytes(b"version 1.0.0 binary")
    artifact_bytes = _make_zip_bytes({"app.exe": b"version 1.1.0 binary"})
    sha256 = hashlib.sha256(artifact_bytes).hexdigest()
    signature = sign_manifest_fields(
        private_key, "1.1.0", "https://cdn.example.invalid/u.zip", sha256, len(artifact_bytes)
    )
    manifest = {
        "version": "1.1.0",
        "download_url": "https://cdn.example.invalid/u.zip",
        "sha256": sha256,
        "size_bytes": len(artifact_bytes),
        "signature": base64.b64encode(signature).decode(),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == _MANIFEST_URL:
            return httpx.Response(200, json=manifest)
        if str(request.url) == "https://cdn.example.invalid/u.zip":
            return httpx.Response(200, content=artifact_bytes)
        return httpx.Response(404)

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    source = ManifestUpdateSource(
        http_client, manifest_url=_MANIFEST_URL, public_key_pem=public_pem
    )
    checker = UpdateChecker(source, current_version=Version.parse("1.0.0"))
    downloader = UpdateDownloader(http_client)
    installer = DirectoryBackupInstaller(app_dir, tmp_path / "backup")
    service = UpdateService(
        checker=checker,
        downloader=downloader,
        installer=installer,
        attempts=attempts,
        downloads=downloads,
        artifact_dir=tmp_path / "artifacts",
    )

    # --- check: origin+signature verified, version genuinely newer ---------
    result = await service.check()
    assert result.update is not None
    assert str(result.update.version) == "1.1.0"

    # --- prepare: real download + real integrity check ----------------------
    attempt = await service.prepare(result.update)
    assert attempt.status is UpdateStatus.READY_TO_INSTALL
    stored_attempt = await attempts.get(attempt.id)
    assert stored_attempt == attempt  # survives the real database round trip

    # --- install: real backup + real extraction ------------------------------
    installed = await service.install(attempt)
    assert installed.status is UpdateStatus.INSTALLED
    assert (app_dir / "app.exe").read_bytes() == b"version 1.1.0 binary"
    assert (tmp_path / "backup" / "app.exe").read_bytes() == b"version 1.0.0 binary"

    # --- a problem is discovered after the fact: roll back for real ---------
    rolled_back = await service.rollback(installed)
    assert rolled_back.status is UpdateStatus.ROLLED_BACK
    assert (app_dir / "app.exe").read_bytes() == b"version 1.0.0 binary"
    final_attempt = await attempts.get(attempt.id)
    assert final_attempt is not None and final_attempt.status is UpdateStatus.ROLLED_BACK


async def test_install_is_genuinely_blocked_by_a_real_in_flight_download(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'app.db'}", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    attempts = SqlUpdateAttemptRepository(session_factory)
    downloads = SqlDownloadRepository(session_factory)
    media = Media(
        kind=MediaKind.VIDEO, ref=PlatformRef(platform=Platform.TWITCH, external_id="v1"), title="t"
    )
    await downloads.save(
        Download(
            media=media,
            destination_path="/x.mp4",
            quality_label="best",
            status=DownloadStatus.DOWNLOADING,
        )
    )

    private_key, public_pem = generate_keypair()
    app_dir = tmp_path / "app"
    artifact_bytes = _make_zip_bytes({"app.exe": b"v2"})
    sha256 = hashlib.sha256(artifact_bytes).hexdigest()
    signature = sign_manifest_fields(
        private_key, "1.1.0", "https://cdn.example.invalid/u.zip", sha256, len(artifact_bytes)
    )
    manifest = {
        "version": "1.1.0",
        "download_url": "https://cdn.example.invalid/u.zip",
        "sha256": sha256,
        "size_bytes": len(artifact_bytes),
        "signature": base64.b64encode(signature).decode(),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == _MANIFEST_URL:
            return httpx.Response(200, json=manifest)
        return httpx.Response(200, content=artifact_bytes)

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    source = ManifestUpdateSource(
        http_client, manifest_url=_MANIFEST_URL, public_key_pem=public_pem
    )
    service = UpdateService(
        checker=UpdateChecker(source, current_version=Version.parse("1.0.0")),
        downloader=UpdateDownloader(http_client),
        installer=DirectoryBackupInstaller(app_dir, tmp_path / "backup"),
        attempts=attempts,
        downloads=downloads,
        artifact_dir=tmp_path / "artifacts",
    )
    result = await service.check()
    assert result.update is not None
    attempt = await service.prepare(result.update)

    try:
        await service.install(attempt)
        raised = False
    except DownloadsInProgressError:
        raised = True
    assert raised
    assert not app_dir.exists()  # never touched


def _make_zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()
