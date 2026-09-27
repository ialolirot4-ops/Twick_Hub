import time

from twick_hub.infrastructure.twitch.integrity_adapter import IntegrityToken, _SettleOnce


def test_integrity_token_is_valid_before_expiry():
    token = IntegrityToken(headers={}, value="abc", expires_at=time.time() + 3600)
    assert token.is_valid() is True


def test_integrity_token_is_invalid_after_expiry():
    token = IntegrityToken(headers={}, value="abc", expires_at=time.time() - 1)
    assert token.is_valid() is False


# FASE 17 — Security + Hardening: regression coverage for the race-condition
# fix in ``IntegrityAdapter._begin_capture``. The Qt-dependent paths
# (timeout timer, blocked/queued interceptor signal, network reply) can't be
# exercised without a real QWebEngineProfile/Chromium — unavailable in this
# sandbox (see this module's own docstring) — but the guard those paths all
# share, ``_SettleOnce``, is plain Python and fully testable in isolation.


def test_settle_once_returns_true_only_on_first_call():
    settle = _SettleOnce()
    assert settle.settle() is True
    assert settle.is_settled is True


def test_settle_once_returns_false_on_every_subsequent_call():
    settle = _SettleOnce()
    settle.settle()
    assert settle.settle() is False
    assert settle.settle() is False
    assert settle.is_settled is True


def test_settle_once_starts_unsettled():
    settle = _SettleOnce()
    assert settle.is_settled is False
