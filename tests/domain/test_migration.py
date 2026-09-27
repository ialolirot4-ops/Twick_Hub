from __future__ import annotations

from datetime import datetime

from twick_hub.domain.enums import LegacyMigrationStatus
from twick_hub.domain.migration import LegacyMigrationRun


def _run(**overrides) -> LegacyMigrationRun:
    fields = {
        "source_path": "/legacy/settings.json",
        "source_sha256": "a" * 64,
        "backup_path": "/backups/settings.json.bak",
    }
    return LegacyMigrationRun(**{**fields, **overrides})


def test_defaults_to_running_and_not_terminal():
    run = _run()
    assert run.status is LegacyMigrationStatus.RUNNING
    assert not run.is_terminal
    assert run.finished_at is None


def test_advanced_to_a_terminal_status_stamps_finished_at():
    run = _run()
    now = datetime(2026, 9, 25, 12, 0)

    advanced = run.advanced(LegacyMigrationStatus.COMPLETED, now=now)

    assert advanced.status is LegacyMigrationStatus.COMPLETED
    assert advanced.is_terminal
    assert advanced.finished_at == now
    assert advanced.id == run.id  # same entity, pure transition


def test_advanced_to_a_non_terminal_status_leaves_finished_at_alone():
    run = _run().advanced(LegacyMigrationStatus.COMPLETED, now=datetime(2026, 9, 25, 12, 0))

    reopened = run.advanced(LegacyMigrationStatus.RUNNING, now=datetime(2026, 9, 25, 13, 0))

    assert reopened.finished_at == run.finished_at


def test_advanced_carries_arbitrary_extra_fields():
    run = _run()

    advanced = run.advanced(
        LegacyMigrationStatus.COMPLETED_WITH_WARNINGS,
        now=datetime(2026, 9, 25, 12, 0),
        settings_migrated=True,
        created_favorite_ids=("f1", "f2"),
        warnings=("something was skipped",),
    )

    assert advanced.settings_migrated is True
    assert advanced.created_favorite_ids == ("f1", "f2")
    assert advanced.warnings == ("something was skipped",)


def test_total_items_created_sums_every_created_id_list():
    run = _run(
        created_favorite_ids=("f1", "f2"),
        created_scheduled_download_ids=("s1",),
        created_download_ids=("d1", "d2", "d3"),
    )

    assert run.total_items_created == 6


def test_total_items_created_is_zero_by_default():
    assert _run().total_items_created == 0


def test_every_terminal_status_is_reported_as_terminal():
    for status in (
        LegacyMigrationStatus.COMPLETED,
        LegacyMigrationStatus.COMPLETED_WITH_WARNINGS,
        LegacyMigrationStatus.FAILED,
        LegacyMigrationStatus.ROLLED_BACK,
    ):
        assert _run(status=status).is_terminal


def test_running_is_the_only_non_terminal_status():
    assert not _run(status=LegacyMigrationStatus.RUNNING).is_terminal
