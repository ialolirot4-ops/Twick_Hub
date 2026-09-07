import time

from twitchlink_next.infrastructure.twitch.integrity_adapter import IntegrityToken


def test_integrity_token_is_valid_before_expiry():
    token = IntegrityToken(headers={}, value="abc", expires_at=time.time() + 3600)
    assert token.is_valid() is True


def test_integrity_token_is_invalid_after_expiry():
    token = IntegrityToken(headers={}, value="abc", expires_at=time.time() - 1)
    assert token.is_valid() is False
