"""Secure token storage for Kick, mirroring
``infrastructure/twitch/token_store.py`` (docs/architecture-decisions.md
AD-07) — same reasoning, same injectable-backend-for-tests design, own
service name so the two platforms' credentials never collide in the
same OS credential store.

Kick's tokens come in a pair (access + refresh) plus an expiry, so this
stores one JSON blob per account rather than a single string.
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import asdict, dataclass
from typing import Protocol

from twick_hub.infrastructure.kick.config import TOKEN_STORE_SERVICE_NAME
from twick_hub.infrastructure.kick.errors import KickAuthError


@dataclass(frozen=True, slots=True)
class StoredKickTokens:
    access_token: str
    refresh_token: str
    expires_at: float  # time.time()-based wall-clock expiry


class _KeyringModule(Protocol):
    def set_password(self, service_name: str, username: str, password: str) -> None: ...

    def get_password(self, service_name: str, username: str) -> str | None: ...

    def delete_password(self, service_name: str, username: str) -> None: ...


class KickTokenStore:
    def __init__(self, keyring_backend: _KeyringModule | None = None) -> None:
        if keyring_backend is None:
            import keyring as _keyring

            keyring_backend = _keyring
        self._keyring = keyring_backend

    def save(self, key: str, tokens: StoredKickTokens) -> None:
        try:
            self._keyring.set_password(TOKEN_STORE_SERVICE_NAME, key, json.dumps(asdict(tokens)))
        except Exception as error:
            raise KickAuthError("Couldn't save Kick tokens to the OS credential store.") from error

    def load(self, key: str) -> StoredKickTokens | None:
        try:
            raw = self._keyring.get_password(TOKEN_STORE_SERVICE_NAME, key)
        except Exception as error:
            raise KickAuthError(
                "Couldn't read Kick tokens from the OS credential store."
            ) from error
        if raw is None:
            return None
        return StoredKickTokens(**json.loads(raw))

    def delete(self, key: str) -> None:
        # Same reasoning as TwitchTokenStore.delete — sign-out must
        # always succeed locally, even if the backend can't confirm it.
        with contextlib.suppress(Exception):
            self._keyring.delete_password(TOKEN_STORE_SERVICE_NAME, key)
