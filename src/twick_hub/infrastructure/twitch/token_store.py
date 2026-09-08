"""Secure token storage via the OS credential store.

docs/architecture-decisions.md AD-07 — confirmed by a concrete finding in
FASE 0: TwitchLink 3.5.5 serializes the OAuth token into plaintext
``settings.json``. This never does that; the token only ever exists in
whatever ``keyring`` resolves to on the user's machine (Windows Credential
Manager, macOS Keychain, or a Linux desktop's Secret Service).

The ``keyring`` module itself is taken as a constructor argument
(defaulting to the real module) purely so tests can supply an in-memory
fake — there is no real credential store available in a headless
container (verified: this sandbox's ``keyring`` resolves to
``keyring.backends.fail.Keyring``, which raises on every call), and that's
expected to be true on some real Linux machines too, not just here.
"""

from __future__ import annotations

import contextlib
from typing import Protocol

from twick_hub.infrastructure.twitch.config import TOKEN_STORE_SERVICE_NAME
from twick_hub.infrastructure.twitch.errors import SecureStorageUnavailableError


class _KeyringModule(Protocol):
    """The subset of the ``keyring`` module's API this class uses —
    typed narrowly so a test fake only has to implement three functions.
    """

    def set_password(self, service_name: str, username: str, password: str) -> None: ...

    def get_password(self, service_name: str, username: str) -> str | None: ...

    def delete_password(self, service_name: str, username: str) -> None: ...


class TwitchTokenStore:
    def __init__(self, keyring_backend: _KeyringModule | None = None) -> None:
        if keyring_backend is None:
            import keyring as _keyring

            keyring_backend = _keyring
        self._keyring = keyring_backend

    def save(self, key: str, token: str) -> None:
        try:
            self._keyring.set_password(TOKEN_STORE_SERVICE_NAME, key, token)
        except Exception as error:
            raise SecureStorageUnavailableError(
                "Couldn't save the Twitch token to the OS credential store. "
                "On Linux, this usually means no Secret Service (gnome-keyring, "
                "KWallet) is running."
            ) from error

    def load(self, key: str) -> str | None:
        try:
            return self._keyring.get_password(TOKEN_STORE_SERVICE_NAME, key)
        except Exception as error:
            raise SecureStorageUnavailableError(
                "Couldn't read the Twitch token from the OS credential store."
            ) from error

    def delete(self, key: str) -> None:
        # Deleting something that was never there (or that a broken
        # backend can't confirm either way) shouldn't block sign-out —
        # the caller's goal ("stop being signed in") is still achieved.
        with contextlib.suppress(Exception):
            self._keyring.delete_password(TOKEN_STORE_SERVICE_NAME, key)
