"""``UpdateSource`` backed by a signed JSON manifest at a pinned HTTPS URL.

Manifest shape (published by release tooling, never by this app):

    {
      "version": "1.2.0",
      "download_url": "https://.../twick-hub-1.2.0.zip",
      "sha256": "<64 lowercase hex chars>",
      "size_bytes": 12345678,
      "release_notes": "...",           # optional
      "published_at": "2026-09-24T00:00:00Z",  # optional, ISO 8601
      "signature": "<base64 Ed25519 signature>"
    }

The signature covers ``f"{version}|{download_url}|{sha256}|{size_bytes}"``
(UTF-8) — exactly the fields that matter security-wise (what to fetch, and
what it must hash to); ``release_notes``/``published_at`` are display-only
and deliberately unsigned, so cosmetic edits don't need a new signature.
"""

from __future__ import annotations

import base64
from datetime import datetime

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key

from twick_hub.domain.updates import UpdateInfo, UpdateOriginError
from twick_hub.domain.version import InvalidVersionError, Version
from twick_hub.infrastructure.updates.config import MANIFEST_URL, PUBLIC_KEY_PEM


def _signed_payload(version: str, download_url: str, sha256: str, size_bytes: int) -> bytes:
    return f"{version}|{download_url}|{sha256}|{size_bytes}".encode()


class ManifestUpdateSource:
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        *,
        manifest_url: str = MANIFEST_URL,
        public_key_pem: bytes = PUBLIC_KEY_PEM,
    ) -> None:
        self._http = http_client
        self._manifest_url = manifest_url
        key = load_pem_public_key(public_key_pem)
        if not isinstance(key, Ed25519PublicKey):
            raise TypeError("configured update public key is not Ed25519")
        self._public_key = key

    async def check(self) -> UpdateInfo | None:
        response = await self._http.get(self._manifest_url)
        if response.status_code == 404:
            return None  # no manifest published yet — not an error
        if response.status_code >= 400:
            raise UpdateOriginError(f"manifest request failed: {response.status_code}")
        try:
            data = response.json()
        except ValueError as exc:
            raise UpdateOriginError(f"manifest is not valid JSON: {exc}") from exc
        return self._verified(data)

    def _verified(self, data: object) -> UpdateInfo:
        if not isinstance(data, dict):
            raise UpdateOriginError("manifest must be a JSON object")
        try:
            version_text = str(data["version"])
            download_url = str(data["download_url"])
            sha256 = str(data["sha256"])
            size_bytes = int(data["size_bytes"])
            signature_b64 = str(data["signature"])
        except (KeyError, TypeError, ValueError) as exc:
            raise UpdateOriginError(f"malformed manifest: {exc}") from exc

        try:
            signature = base64.b64decode(signature_b64, validate=True)
        except (ValueError, TypeError) as exc:
            raise UpdateOriginError(f"malformed signature encoding: {exc}") from exc

        payload = _signed_payload(version_text, download_url, sha256, size_bytes)
        try:
            self._public_key.verify(signature, payload)
        except InvalidSignature as exc:
            raise UpdateOriginError("manifest signature does not verify") from exc

        try:
            version = Version.parse(version_text)
        except InvalidVersionError as exc:
            raise UpdateOriginError(f"manifest version is invalid: {exc}") from exc

        published_at = None
        raw_published_at = data.get("published_at")
        if raw_published_at is not None:
            try:
                published_at = datetime.fromisoformat(str(raw_published_at))
            except ValueError as exc:
                raise UpdateOriginError(f"manifest published_at is invalid: {exc}") from exc

        try:
            return UpdateInfo(
                version=version,
                download_url=download_url,
                sha256=sha256,
                size_bytes=size_bytes,
                release_notes=data.get("release_notes"),
                published_at=published_at,
            )
        except ValueError as exc:  # UpdateInfo.__post_init__: https-only, hex sha256, etc.
            raise UpdateOriginError(f"verified manifest failed validation: {exc}") from exc
