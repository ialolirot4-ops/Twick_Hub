import pytest

from twick_hub.infrastructure.kick.errors import KickAuthError
from twick_hub.infrastructure.kick.token_store import KickTokenStore, StoredKickTokens


class FakeKeyring:
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


_TOKENS = StoredKickTokens(access_token="a1", refresh_token="r1", expires_at=1234.0)


def test_save_then_load_round_trips():
    store = KickTokenStore(FakeKeyring())
    store.save("user-tokens", _TOKENS)
    assert store.load("user-tokens") == _TOKENS


def test_load_missing_key_returns_none():
    store = KickTokenStore(FakeKeyring())
    assert store.load("user-tokens") is None


def test_delete_removes_it():
    store = KickTokenStore(FakeKeyring())
    store.save("user-tokens", _TOKENS)
    store.delete("user-tokens")
    assert store.load("user-tokens") is None


def test_broken_backend_raises_on_save():
    store = KickTokenStore(FakeKeyring(broken=True))
    with pytest.raises(KickAuthError):
        store.save("user-tokens", _TOKENS)


def test_broken_backend_delete_is_silently_tolerated():
    store = KickTokenStore(FakeKeyring(broken=True))
    store.delete("user-tokens")  # must not raise
