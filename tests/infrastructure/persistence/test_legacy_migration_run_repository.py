from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import sessionmaker

from twick_hub.domain.enums import LegacyMigrationStatus
from twick_hub.domain.migration import LegacyMigrationRun
from twick_hub.infrastructure.persistence.legacy_migration_run_repository import (
    SqlLegacyMigrationRunRepository,
)

_SHA = "a" * 64


def _run(**overrides) -> LegacyMigrationRun:
    fields = {
        "source_path": "/legacy/settings.json",
        "source_sha256": _SHA,
        "backup_path": "/backups/settings.json.bak",
    }
    return LegacyMigrationRun(**{**fields, **overrides})


async def test_get_returns_none_when_absent(session_factory: sessionmaker):
    repo = SqlLegacyMigrationRunRepository(session_factory)
    assert await repo.get("nope") is None


async def test_save_then_get_round_trips_every_field(session_factory: sessionmaker):
    repo = SqlLegacyMigrationRunRepository(session_factory)
    run = _run(
        status=LegacyMigrationStatus.COMPLETED_WITH_WARNINGS,
        started_at=datetime(2026, 9, 25, 10, 0),
        finished_at=datetime(2026, 9, 25, 10, 5),
        settings_migrated=True,
        previous_settings_json='{"theme": "system"}',
        account_token_migrated=True,
        created_favorite_ids=("f1", "f2"),
        created_scheduled_download_ids=("s1",),
        created_download_ids=("d1", "d2", "d3"),
        skipped_bookmark_logins=("ninja",),
        skipped_scheduled_download_logins=("baduser",),
        warnings=("a warning", "another warning"),
        error_message=None,
    )

    await repo.save(run)
    fetched = await repo.get(run.id)

    assert fetched == run


async def test_save_twice_updates_the_same_row(session_factory: sessionmaker):
    repo = SqlLegacyMigrationRunRepository(session_factory)
    run = _run()
    await repo.save(run)

    updated = run.advanced(
        LegacyMigrationStatus.FAILED, now=datetime(2026, 9, 25, 10, 5), error_message="boom"
    )
    await repo.save(updated)

    fetched = await repo.get(run.id)
    assert fetched is not None
    assert fetched.status is LegacyMigrationStatus.FAILED
    assert fetched.error_message == "boom"


async def test_optional_fields_round_trip_as_none_or_empty(session_factory: sessionmaker):
    repo = SqlLegacyMigrationRunRepository(session_factory)
    run = _run()

    await repo.save(run)
    fetched = await repo.get(run.id)

    assert fetched is not None
    assert fetched.finished_at is None
    assert fetched.previous_settings_json is None
    assert fetched.error_message is None
    assert fetched.created_favorite_ids == ()
    assert fetched.created_scheduled_download_ids == ()
    assert fetched.created_download_ids == ()
    assert fetched.skipped_bookmark_logins == ()
    assert fetched.skipped_scheduled_download_logins == ()
    assert fetched.warnings == ()


async def test_list_all_orders_newest_first(session_factory: sessionmaker):
    repo = SqlLegacyMigrationRunRepository(session_factory)
    older = _run(source_sha256="b" * 64, started_at=datetime(2026, 9, 20, 0, 0))
    newer = _run(source_sha256="c" * 64, started_at=datetime(2026, 9, 24, 0, 0))
    await repo.save(older)
    await repo.save(newer)

    result = await repo.list_all()

    assert [r.id for r in result] == [newer.id, older.id]


async def test_list_all_respects_limit_and_offset(session_factory: sessionmaker):
    repo = SqlLegacyMigrationRunRepository(session_factory)
    for day in range(5):
        await repo.save(
            _run(source_sha256=f"{day}" * 64, started_at=datetime(2026, 9, 20 + day, 0, 0))
        )

    page = await repo.list_all(limit=2, offset=1)

    assert len(page) == 2


async def test_find_by_source_hash_returns_none_when_no_run_matches(session_factory: sessionmaker):
    repo = SqlLegacyMigrationRunRepository(session_factory)
    assert await repo.find_by_source_hash(_SHA) is None


async def test_find_by_source_hash_finds_the_matching_run(session_factory: sessionmaker):
    repo = SqlLegacyMigrationRunRepository(session_factory)
    run = _run()
    await repo.save(run)

    found = await repo.find_by_source_hash(_SHA)

    assert found == run


async def test_find_by_source_hash_returns_the_newest_when_several_share_a_hash(
    session_factory: sessionmaker,
):
    repo = SqlLegacyMigrationRunRepository(session_factory)
    first = _run(started_at=datetime(2026, 9, 20, 0, 0))
    await repo.save(first)
    rolled_back = first.advanced(
        LegacyMigrationStatus.ROLLED_BACK, now=datetime(2026, 9, 21, 0, 0)
    )
    await repo.save(rolled_back)
    second = _run(started_at=datetime(2026, 9, 22, 0, 0))
    await repo.save(second)

    found = await repo.find_by_source_hash(_SHA)

    assert found is not None
    assert found.started_at == datetime(2026, 9, 22, 0, 0)


async def test_a_warning_containing_a_comma_round_trips_intact(session_factory: sessionmaker):
    """created_*_ids are comma-joined (mappers.py); warnings are newline-
    joined precisely so a warning message is free to contain a comma."""
    repo = SqlLegacyMigrationRunRepository(session_factory)
    run = _run(warnings=("channel a, b and c could not be resolved",))

    await repo.save(run)
    fetched = await repo.get(run.id)

    assert fetched is not None
    assert fetched.warnings == ("channel a, b and c could not be resolved",)
