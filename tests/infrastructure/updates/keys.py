"""A throwaway Ed25519 keypair used only in tests to sign manifests, so
``ManifestUpdateSource`` can be tested against real signature
verification instead of a mocked crypto call. This has no relationship
to the actual key embedded in ``infrastructure.updates.config`` — tests
that exercise the real config module's key use its own PUBLIC_KEY_PEM,
signed with a matching TEST_PRIVATE_KEY generated the same way (see
test_manifest_source.py for how they're kept in sync).
"""

from __future__ import annotations

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def generate_keypair() -> tuple[Ed25519PrivateKey, bytes]:
    """Returns (private_key, public_key_pem)."""
    private_key = Ed25519PrivateKey.generate()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_key, public_pem


def sign_manifest_fields(
    private_key: Ed25519PrivateKey, version: str, download_url: str, sha256: str, size_bytes: int
) -> bytes:
    payload = f"{version}|{download_url}|{sha256}|{size_bytes}".encode()
    return private_key.sign(payload)
