"""FASE 18 — Testing: ``IntegrityAdapter`` itself (as opposed to the
``IntegrityToken``/``_SettleOnce`` dataclasses in test_integrity_token.py)
had zero coverage — every test there only touches free-standing helpers,
never actually constructs the class. ``_begin_capture`` genuinely can't be
exercised here (needs a real Chromium renderer, and this sandbox's
Chromium refuses to run as root without ``--no-sandbox`` — see this
module's own docstring and docs/risk-register.md RISK-TWITCH-04), but
everything around it — the cache check, the cache-hit short-circuit, and
the asyncio bridge — needs nothing Twitch- or WebEngine-specific at all.
"""

from __future__ import annotations

import time

import pytest
from PySide6 import QtNetwork

from twick_hub.infrastructure.twitch.errors import IntegrityUnavailableError
from twick_hub.infrastructure.twitch.integrity_adapter import (
    IntegrityAdapter,
    IntegrityHeaderSource,
    IntegrityToken,
)


def _adapter(qapp) -> IntegrityAdapter:
    network = QtNetwork.QNetworkAccessManager()
    return IntegrityAdapter(network, lambda: "user-oauth-token")


def test_has_valid_integrity_is_false_with_no_cache(qapp):
    assert _adapter(qapp).has_valid_integrity() is False


def test_has_valid_integrity_is_true_with_a_fresh_cached_token(qapp):
    adapter = _adapter(qapp)
    adapter._cached = IntegrityToken(headers={}, value="v", expires_at=time.time() + 3600)
    assert adapter.has_valid_integrity() is True


def test_has_valid_integrity_is_false_with_an_expired_cached_token(qapp):
    adapter = _adapter(qapp)
    adapter._cached = IntegrityToken(headers={}, value="v", expires_at=time.time() - 1)
    assert adapter.has_valid_integrity() is False


def test_get_integrity_returns_the_cache_without_starting_a_new_capture(qapp):
    adapter = _adapter(qapp)
    cached = IntegrityToken(headers={"a": "b"}, value="v", expires_at=time.time() + 3600)
    adapter._cached = cached

    def _must_not_be_called(_callback):
        raise AssertionError("must not start a capture while the cache is still valid")

    adapter._begin_capture = _must_not_be_called  # type: ignore[method-assign]

    seen: list[IntegrityToken | None] = []
    adapter.get_integrity(seen.append)

    assert seen == [cached]


def test_get_integrity_starts_a_capture_when_the_cache_is_empty(qapp):
    adapter = _adapter(qapp)
    started: list[object] = []
    adapter._begin_capture = lambda callback: started.append(callback)  # type: ignore[method-assign]

    adapter.get_integrity(lambda token: None)

    assert len(started) == 1


async def test_get_integrity_async_returns_the_cached_token(qapp):
    adapter = _adapter(qapp)
    token = IntegrityToken(headers={}, value="v", expires_at=time.time() + 3600)
    adapter.get_integrity = lambda callback: callback(token)  # type: ignore[method-assign]

    assert await adapter.get_integrity_async() is token


async def test_get_integrity_async_raises_when_capture_yields_nothing(qapp):
    adapter = _adapter(qapp)
    adapter.get_integrity = lambda callback: callback(None)  # type: ignore[method-assign]

    with pytest.raises(IntegrityUnavailableError):
        await adapter.get_integrity_async()


# FASE 21c — ``IntegrityHeaderSource`` is what ``TwitchGQLClient`` actually
# calls in production. Same shape as TwitchLink 3.5.6's
# ``IntegrityToken.getHeaders()``: captured headers + ``Client-Integrity``.


class _FakeIntegrityAdapter:
    def __init__(self, token: IntegrityToken | None) -> None:
        self._token = token

    async def get_integrity_async(self) -> IntegrityToken:
        if self._token is None:
            raise IntegrityUnavailableError("no token")
        return self._token


async def test_header_source_adds_client_integrity_to_the_captured_headers():
    token = IntegrityToken(
        headers={"Client-ID": "cid", "Authorization": "OAuth abc"},
        value="integrity-value",
        expires_at=9_999_999_999.0,
    )
    source = IntegrityHeaderSource(_FakeIntegrityAdapter(token))

    headers = await source.get_headers()

    assert headers == {
        "Client-ID": "cid",
        "Authorization": "OAuth abc",
        "Client-Integrity": "integrity-value",
    }
    assert "Client-Integrity" not in token.headers  # the token itself is not mutated


async def test_header_source_propagates_integrity_unavailable():
    source = IntegrityHeaderSource(_FakeIntegrityAdapter(None))
    with pytest.raises(IntegrityUnavailableError):
        await source.get_headers()
