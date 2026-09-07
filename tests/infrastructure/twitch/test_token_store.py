import pytest

from twitchlink_next.infrastructure.twitch.errors import SecureStorageUnavailableError
from twitchlink_next.infrastructure.twitch.token_store import TwitchTokenStore


class FakeKeyring:
    """In-memory stand-in for the ``keyring`` module's API. Real usage
    against an actual OS credential store is out of scope for automated
    tests — see token_store.py's module docstring."""

    def __init__(self, *, broken: bool = False) -> None:
        self._data: dict[tuple[str, str], str] = {}
        self._broken = broken

    def set_password(self, service_name: str, username: str, password: str) -> None:
        if self._broken:
            raise RuntimeError("no backend available")
        self._data[(service_name, username)] = password

    def get_password(self, service_name: str, username: str) -> str | None:
        if self._broken:
            raise RuntimeError("no backend available")
        return self._data.get((service_name, username))

    def delete_password(self, service_name: str, username: str) -> None:
        if self._broken:
            raise RuntimeError("no backend available")
        self._data.pop((service_name, username), None)


def test_save_then_load_round_trips():
    store = TwitchTokenStore(FakeKeyring())
    store.save("user-session-token", "abc123")
    assert store.load("user-session-token") == "abc123"


def test_load_missing_key_returns_none():
    store = TwitchTokenStore(FakeKeyring())
    assert store.load("nothing-saved-yet") is None


def test_delete_removes_it():
    store = TwitchTokenStore(FakeKeyring())
    store.save("user-session-token", "abc123")
    store.delete("user-session-token")
    assert store.load("user-session-token") is None


def test_delete_of_missing_key_does_not_raise():
    store = TwitchTokenStore(FakeKeyring())
    store.delete("was-never-there")  # must not raise


def test_broken_backend_raises_secure_storage_error_on_save():
    store = TwitchTokenStore(FakeKeyring(broken=True))
    with pytest.raises(SecureStorageUnavailableError):
        store.save("user-session-token", "abc123")


def test_broken_backend_raises_secure_storage_error_on_load():
    store = TwitchTokenStore(FakeKeyring(broken=True))
    with pytest.raises(SecureStorageUnavailableError):
        store.load("user-session-token")


def test_broken_backend_delete_is_silently_tolerated():
    """Signing out must always succeed locally, even if the credential
    store can't confirm the deletion — see token_store.py's delete()."""
    store = TwitchTokenStore(FakeKeyring(broken=True))
    store.delete("user-session-token")  # must not raise
