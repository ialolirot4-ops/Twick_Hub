"""Update-source configuration and the app's trusted public key.

The keypair here is a genuine Ed25519 keypair generated for this project
(FASE 14), not a placeholder string — but it's a **development/test**
keypair only. Before any real release, ``PUBLIC_KEY_PEM`` must be replaced
with the project's actual release-signing public key, and the matching
private key must live only in release tooling (CI secrets, an offline
signing step) — never in this repository. Nothing here can tell the
difference between "the real key" and "a key" by construction; that
distinction is an operational one for whoever runs a release.
"""

from __future__ import annotations

# Pinned host: a manifest is only ever trusted from exactly this origin —
# "verificar origen" (Master Plan §51) starts here, before the signature
# is even checked, so a redirect to a different host is rejected outright
# rather than silently followed.
MANIFEST_URL = "https://updates.twickhub.example/manifest.json"

# The app's own Ed25519 public key (SubjectPublicKeyInfo, PEM). See this
# module's docstring — a real release key belongs here instead.
PUBLIC_KEY_PEM = b"""-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAyOYNCFO77+3DrbH5yFJJqee0hMyavNQwjFHdM5bNo3M=
-----END PUBLIC KEY-----
"""
