from __future__ import annotations

import base64

import httpx
import pytest

from tests.infrastructure.updates.keys import generate_keypair, sign_manifest_fields
from twick_hub.domain.updates import UpdateOriginError
from twick_hub.infrastructure.updates.manifest_source import ManifestUpdateSource

_URL = "https://updates.example.invalid/manifest.json"
_SHA = "b" * 64


def _manifest(
    private_key,
    *,
    version="1.1.0",
    download_url="https://cdn.example.invalid/u.zip",
    sha256=_SHA,
    size_bytes=1000,
    **extra,
):
    signature = sign_manifest_fields(private_key, version, download_url, sha256, size_bytes)
    return {
        "version": version,
        "download_url": download_url,
        "sha256": sha256,
        "size_bytes": size_bytes,
        "signature": base64.b64encode(signature).decode(),
        **extra,
    }


def _source(handler, public_key_pem):
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return ManifestUpdateSource(http_client, manifest_url=_URL, public_key_pem=public_key_pem)


async def test_a_correctly_signed_manifest_is_accepted():
    private_key, public_pem = generate_keypair()
    manifest = _manifest(private_key, release_notes="fixes stuff")

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == _URL
        return httpx.Response(200, json=manifest)

    info = await _source(handler, public_pem).check()

    assert info is not None
    assert str(info.version) == "1.1.0"
    assert info.sha256 == _SHA
    assert info.release_notes == "fixes stuff"


async def test_a_404_means_no_update_published_yet():
    private_key, public_pem = generate_keypair()
    info = await _source(lambda r: httpx.Response(404), public_pem).check()
    assert info is None


async def test_a_server_error_raises_origin_error():
    private_key, public_pem = generate_keypair()
    with pytest.raises(UpdateOriginError):
        await _source(lambda r: httpx.Response(500), public_pem).check()


async def test_invalid_json_raises_origin_error():
    private_key, public_pem = generate_keypair()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    with pytest.raises(UpdateOriginError):
        await _source(handler, public_pem).check()


async def test_a_manifest_signed_with_the_wrong_key_is_rejected():
    signing_key, _ = generate_keypair()
    _, trusted_public_pem = generate_keypair()  # a different keypair
    manifest = _manifest(signing_key)

    with pytest.raises(UpdateOriginError, match="signature"):
        await _source(lambda r: httpx.Response(200, json=manifest), trusted_public_pem).check()


async def test_tampering_with_any_signed_field_invalidates_the_signature():
    private_key, public_pem = generate_keypair()
    manifest = _manifest(private_key)
    manifest["download_url"] = "https://attacker.invalid/evil.zip"  # signed field, now mismatched

    with pytest.raises(UpdateOriginError, match="signature"):
        await _source(lambda r: httpx.Response(200, json=manifest), public_pem).check()


async def test_tampering_with_size_bytes_invalidates_the_signature():
    private_key, public_pem = generate_keypair()
    manifest = _manifest(private_key)
    manifest["size_bytes"] = 999999  # signed field, now mismatched

    with pytest.raises(UpdateOriginError, match="signature"):
        await _source(lambda r: httpx.Response(200, json=manifest), public_pem).check()


async def test_release_notes_can_change_without_invalidating_the_signature():
    """release_notes/published_at are deliberately unsigned (see
    manifest_source.py's module docstring)."""
    private_key, public_pem = generate_keypair()
    manifest = _manifest(private_key, release_notes="v1")
    manifest["release_notes"] = "v2, edited after signing"

    info = await _source(lambda r: httpx.Response(200, json=manifest), public_pem).check()

    assert info is not None and info.release_notes == "v2, edited after signing"


async def test_malformed_signature_encoding_raises_origin_error():
    private_key, public_pem = generate_keypair()
    manifest = _manifest(private_key)
    manifest["signature"] = "not-valid-base64!!!"

    with pytest.raises(UpdateOriginError):
        await _source(lambda r: httpx.Response(200, json=manifest), public_pem).check()


@pytest.mark.parametrize(
    "missing_field", ["version", "download_url", "sha256", "size_bytes", "signature"]
)
async def test_a_missing_field_raises_origin_error(missing_field):
    private_key, public_pem = generate_keypair()
    manifest = _manifest(private_key)
    del manifest[missing_field]

    with pytest.raises(UpdateOriginError):
        await _source(lambda r: httpx.Response(200, json=manifest), public_pem).check()


async def test_a_non_object_manifest_raises_origin_error():
    private_key, public_pem = generate_keypair()

    with pytest.raises(UpdateOriginError):
        await _source(lambda r: httpx.Response(200, json=[1, 2, 3]), public_pem).check()


async def test_an_invalid_version_string_raises_origin_error():
    private_key, public_pem = generate_keypair()
    manifest = _manifest(private_key, version="not-a-version")

    with pytest.raises(UpdateOriginError, match="version"):
        await _source(lambda r: httpx.Response(200, json=manifest), public_pem).check()


async def test_a_non_https_download_url_raises_origin_error():
    private_key, public_pem = generate_keypair()
    manifest = _manifest(private_key, download_url="http://insecure.invalid/u.zip")

    with pytest.raises(UpdateOriginError):
        await _source(lambda r: httpx.Response(200, json=manifest), public_pem).check()


async def test_published_at_is_parsed_when_present():
    private_key, public_pem = generate_keypair()
    manifest = _manifest(private_key, published_at="2026-09-24T10:00:00")

    info = await _source(lambda r: httpx.Response(200, json=manifest), public_pem).check()

    assert info is not None
    assert info.published_at is not None and info.published_at.year == 2026


async def test_an_invalid_published_at_raises_origin_error():
    private_key, public_pem = generate_keypair()
    manifest = _manifest(private_key, published_at="not-a-real-date")

    with pytest.raises(UpdateOriginError, match="published_at"):
        await _source(lambda r: httpx.Response(200, json=manifest), public_pem).check()


def test_a_non_ed25519_public_key_is_rejected_at_construction():
    """The manifest's signature scheme is a fixed architectural decision
    (Ed25519, this module's own docstring) — a misconfigured RSA/EC key
    must fail loudly and immediately, not be silently accepted and fail
    signature verification on every single manifest later."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rsa_public_pem = rsa_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(404)))

    with pytest.raises(TypeError, match="Ed25519"):
        ManifestUpdateSource(http_client, manifest_url=_URL, public_key_pem=rsa_public_pem)


async def test_the_configured_public_key_and_manifest_url_are_used_by_default():
    from twick_hub.infrastructure.updates.config import MANIFEST_URL

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(404)))
    source = ManifestUpdateSource(http_client)  # no overrides

    seen_urls = []

    async def spy_handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(404)

    source._http = httpx.AsyncClient(transport=httpx.MockTransport(spy_handler))
    await source.check()

    assert seen_urls == [MANIFEST_URL]
