from __future__ import annotations

from tests.application.fakes import FakeUpdateSource
from twick_hub.application.updates.checker import UpdateChecker
from twick_hub.domain.updates import UpdateInfo, UpdateOriginError
from twick_hub.domain.version import Version

_SHA = "c" * 64


def _info(version: str) -> UpdateInfo:
    return UpdateInfo(
        version=Version.parse(version),
        download_url="https://example.invalid/u.zip",
        sha256=_SHA,
        size_bytes=100,
    )


async def test_reports_no_update_when_the_source_has_nothing_published():
    checker = UpdateChecker(FakeUpdateSource(info=None), Version.parse("1.0.0"))

    result = await checker.check()

    assert result.update is None
    assert result.current_version == Version.parse("1.0.0")


async def test_reports_an_update_when_the_manifest_is_newer():
    checker = UpdateChecker(FakeUpdateSource(info=_info("1.1.0")), Version.parse("1.0.0"))

    result = await checker.check()

    assert result.update is not None and str(result.update.version) == "1.1.0"


async def test_does_not_report_an_update_for_the_same_version():
    checker = UpdateChecker(FakeUpdateSource(info=_info("1.0.0")), Version.parse("1.0.0"))

    result = await checker.check()

    assert result.update is None


async def test_does_not_report_an_update_for_an_older_version():
    """Guards against a replayed old-but-validly-signed manifest (see
    checker.py's module docstring) as much as it guards against a genuine
    older release."""
    checker = UpdateChecker(FakeUpdateSource(info=_info("0.9.0")), Version.parse("1.0.0"))

    result = await checker.check()

    assert result.update is None


async def test_a_prerelease_of_the_current_version_is_not_reported_as_an_update():
    checker = UpdateChecker(FakeUpdateSource(info=_info("1.0.0-rc1")), Version.parse("1.0.0"))

    result = await checker.check()

    assert result.update is None


async def test_an_origin_error_from_the_source_propagates():
    import pytest

    checker = UpdateChecker(
        FakeUpdateSource(error=UpdateOriginError("bad signature")), Version.parse("1.0.0")
    )

    with pytest.raises(UpdateOriginError):
        await checker.check()
