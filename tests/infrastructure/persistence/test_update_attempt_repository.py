from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import sessionmaker

from twick_hub.domain.enums import UpdateStatus
from twick_hub.domain.updates import UpdateAttempt
from twick_hub.domain.version import Version
from twick_hub.infrastructure.persistence.update_attempt_repository import (
    SqlUpdateAttemptRepository,
)

_SHA = "e" * 64


def _attempt(**overrides) -> UpdateAttempt:
    fields = {
        "from_version": Version.parse("1.0.0"),
        "to_version": Version.parse("1.1.0"),
        "download_url": "https://example.invalid/u.zip",
        "sha256": _SHA,
    }
    return UpdateAttempt(**{**fields, **overrides})


async def test_get_returns_none_when_absent(session_factory: sessionmaker):
    repo = SqlUpdateAttemptRepository(session_factory)
    assert await repo.get("nope") is None


async def test_save_then_get_round_trips_every_field(session_factory: sessionmaker):
    repo = SqlUpdateAttemptRepository(session_factory)
    attempt = _attempt(
        status=UpdateStatus.INSTALLED,
        artifact_path="/tmp/u.zip",
        backup_path="/tmp/backup",
        error_message=None,
        started_at=datetime(2026, 9, 24, 10, 0),
        finished_at=datetime(2026, 9, 24, 10, 5),
    )

    await repo.save(attempt)
    fetched = await repo.get(attempt.id)

    assert fetched == attempt


async def test_save_twice_updates_the_same_row(session_factory: sessionmaker):
    repo = SqlUpdateAttemptRepository(session_factory)
    attempt = _attempt()
    await repo.save(attempt)

    updated = attempt.advanced(
        UpdateStatus.FAILED, now=datetime(2026, 9, 24, 10, 5), error_message="x"
    )
    await repo.save(updated)

    fetched = await repo.get(attempt.id)
    assert fetched is not None
    assert fetched.status is UpdateStatus.FAILED and fetched.error_message == "x"


async def test_list_all_orders_newest_first(session_factory: sessionmaker):
    repo = SqlUpdateAttemptRepository(session_factory)
    older = _attempt(started_at=datetime(2026, 9, 20, 0, 0))
    newer = _attempt(started_at=datetime(2026, 9, 24, 0, 0))
    await repo.save(older)
    await repo.save(newer)

    result = await repo.list_all()

    assert [a.id for a in result] == [newer.id, older.id]


async def test_list_all_respects_limit_and_offset(session_factory: sessionmaker):
    repo = SqlUpdateAttemptRepository(session_factory)
    for day in range(5):
        await repo.save(_attempt(started_at=datetime(2026, 9, 20 + day, 0, 0)))

    page = await repo.list_all(limit=2, offset=1)

    assert len(page) == 2


async def test_optional_fields_round_trip_as_none(session_factory: sessionmaker):
    repo = SqlUpdateAttemptRepository(session_factory)
    attempt = _attempt()
    await repo.save(attempt)

    fetched = await repo.get(attempt.id)

    assert fetched is not None
    assert fetched.artifact_path is None
    assert fetched.backup_path is None
    assert fetched.error_message is None
    assert fetched.finished_at is None


async def test_prerelease_versions_round_trip(session_factory: sessionmaker):
    repo = SqlUpdateAttemptRepository(session_factory)
    attempt = _attempt(from_version=Version.parse("1.0.0-rc1"), to_version=Version.parse("1.0.0"))

    await repo.save(attempt)
    fetched = await repo.get(attempt.id)

    assert fetched is not None
    assert str(fetched.from_version) == "1.0.0-rc1"
