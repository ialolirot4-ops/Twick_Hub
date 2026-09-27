"""Downloads a verified update artifact and checks its integrity.

Deliberately its own small, independent HTTP client rather than routed
through ``infrastructure/downloads/`` (``DownloadQueue``/
``DownloadCoordinator``/``DownloadExecutor``) — that engine exists for the
user's own stream/VOD/clip downloads, and Master Plan §51 is explicit:
"No interferir con descargas activas." Sharing workers or a queue with
those downloads is exactly the interference that line rules out; a
separate, direct fetch can never compete with them for a worker slot.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import httpx

from twick_hub.domain.updates import UpdateInfo, UpdateIntegrityError

_CHUNK_SIZE = 1024 * 1024  # 1 MiB


class UpdateDownloader:
    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._http = http_client

    async def download(self, info: UpdateInfo, destination: Path) -> Path:
        """Streams the artifact to ``destination`` and verifies its
        SHA-256 against ``info.sha256`` before returning. The partial file
        is removed on any failure — a half-written or integrity-failed
        artifact must never be mistaken for a usable one."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        try:
            async with self._http.stream("GET", info.download_url) as response:
                response.raise_for_status()
                with destination.open("wb") as handle:
                    async for chunk in response.aiter_bytes(_CHUNK_SIZE):
                        handle.write(chunk)
                        digest.update(chunk)
        except Exception:
            destination.unlink(missing_ok=True)
            raise

        actual = digest.hexdigest()
        if actual != info.sha256:
            destination.unlink(missing_ok=True)
            raise UpdateIntegrityError(
                f"downloaded artifact sha256 {actual} does not match manifest {info.sha256}"
            )
        return destination
