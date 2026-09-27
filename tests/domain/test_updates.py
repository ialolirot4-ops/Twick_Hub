from __future__ import annotations

from datetime import datetime

import pytest

from twick_hub.domain.enums import UpdateStatus
from twick_hub.domain.updates import UpdateAttempt, UpdateInfo
from twick_hub.domain.version import Version

_SHA = "a" * 64


def _info(**overrides) -> UpdateInfo:
    fields = {
        "version": Version.parse("1.1.0"),
        "download_url": "https://example.invalid/update.zip",
        "sha256": _SHA,
        "size_bytes": 1000,
    }
    return UpdateInfo(**{**fields, **overrides})


# --- UpdateInfo --------------------------------------------------------


def test_valid_info_constructs():
    info = _info()
    assert info.sha256 == _SHA


def test_sha256_is_lowercased():
    info = _info(sha256="A" * 64)
    assert info.sha256 == "a" * 64


@pytest.mark.parametrize("sha", ["short", "g" * 64, "A" * 63, "A" * 65, ""])
def test_invalid_sha256_is_rejected(sha):
    with pytest.raises(ValueError):
        _info(sha256=sha)


def test_non_https_download_url_is_rejected():
    with pytest.raises(ValueError, match="https"):
        _info(download_url="http://example.invalid/update.zip")


@pytest.mark.parametrize("size", [0, -1])
def test_non_positive_size_is_rejected(size):
    with pytest.raises(ValueError):
        _info(size_bytes=size)


# --- UpdateAttempt -------------------------------------------------------


def _attempt(**overrides) -> UpdateAttempt:
    fields = {
        "from_version": Version.parse("1.0.0"),
        "to_version": Version.parse("1.1.0"),
        "download_url": "https://example.invalid/update.zip",
        "sha256": _SHA,
    }
    return UpdateAttempt(**{**fields, **overrides})


def test_default_status_is_available():
    assert _attempt().status is UpdateStatus.AVAILABLE


def test_advanced_returns_a_new_instance_with_the_new_status():
    attempt = _attempt()
    now = datetime(2026, 9, 24, 10, 0)

    advanced = attempt.advanced(UpdateStatus.DOWNLOADING, now=now)

    assert attempt.status is UpdateStatus.AVAILABLE  # original untouched
    assert advanced.status is UpdateStatus.DOWNLOADING
    assert advanced.id == attempt.id


@pytest.mark.parametrize(
    "status", [UpdateStatus.INSTALLED, UpdateStatus.FAILED, UpdateStatus.ROLLED_BACK]
)
def test_terminal_statuses_stamp_finished_at(status):
    now = datetime(2026, 9, 24, 10, 0)
    advanced = _attempt().advanced(status, now=now)
    assert advanced.finished_at == now


@pytest.mark.parametrize(
    "status",
    [
        UpdateStatus.DOWNLOADING,
        UpdateStatus.VERIFYING,
        UpdateStatus.READY_TO_INSTALL,
        UpdateStatus.INSTALLING,
    ],
)
def test_non_terminal_statuses_leave_finished_at_unset(status):
    advanced = _attempt().advanced(status, now=datetime(2026, 9, 24, 10, 0))
    assert advanced.finished_at is None


def test_advanced_accepts_extra_fields():
    advanced = _attempt().advanced(
        UpdateStatus.FAILED, now=datetime(2026, 9, 24, 10, 0), error_message="boom"
    )
    assert advanced.error_message == "boom"
