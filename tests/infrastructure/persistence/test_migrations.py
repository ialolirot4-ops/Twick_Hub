"""Every other test in this package builds its schema with
``Base.metadata.create_all()`` — fast, but it would stay green even if the
checked-in Alembic migration drifted from models.py. This file runs the
*real* migration (as a subprocess, exactly how a user's machine would)
against a fresh SQLite file, then proves the two agree by running real
repository CRUD against that exact migrated schema.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from twick_hub.domain.enums import Platform
from twick_hub.domain.identity import Channel, User
from twick_hub.domain.value_objects import PlatformRef
from twick_hub.infrastructure.persistence.channel_repository import SqlChannelRepository

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _run_alembic(*args: str, db_path: Path) -> None:
    env = {**os.environ, "TWICK_HUB_DATABASE_URL": f"sqlite:///{db_path}"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _tables_in(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name != 'alembic_version'"
        ).fetchall()
    finally:
        conn.close()
    return {row[0] for row in rows}


async def test_migration_upgrade_creates_a_schema_repositories_can_use(tmp_path: Path):
    db_path = tmp_path / "migrated.db"
    _run_alembic("upgrade", "head", db_path=db_path)

    assert _tables_in(db_path) == {
        "channels",
        "favorites",
        "playlists",
        "playlist_items",
        "scheduled_downloads",
        "notifications",
        "downloads",
        "settings",
        "update_attempts",
        "legacy_migration_runs",
    }

    engine = create_engine(f"sqlite:///{db_path}", future=True)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    repo = SqlChannelRepository(session_factory)

    ref = PlatformRef(platform=Platform.TWITCH, external_id="c1")
    channel = Channel(ref=ref, user=User(ref=ref, username="x", display_name="X"))
    await repo.save(channel)

    assert await repo.get(ref) == channel


def test_migration_downgrade_removes_every_table(tmp_path: Path):
    db_path = tmp_path / "migrated.db"
    _run_alembic("upgrade", "head", db_path=db_path)

    _run_alembic("downgrade", "base", db_path=db_path)

    assert _tables_in(db_path) == set()


def test_upgrading_with_pre_existing_favorites_data_does_not_fail(tmp_path: Path):
    """Regression test: the second migration originally added `position`
    as NOT NULL with no server_default, which fails on SQLite the moment
    a favorites row already exists (ALTER TABLE ADD COLUMN ... NOT NULL
    with no default). Caught by testing against real data instead of only
    ever upgrading a brand-new, empty database."""
    db_path = tmp_path / "migrated.db"
    _run_alembic("upgrade", "655768f323e3", db_path=db_path)  # the first migration only

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO favorites (id, channel_platform, channel_external_id, "
            "notify_on_live, auto_download, added_at) "
            "VALUES ('f1', 'twitch', '123', 1, 0, '2026-01-01 00:00:00')"
        )
        conn.commit()
    finally:
        conn.close()

    _run_alembic("upgrade", "head", db_path=db_path)  # must not raise

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT position FROM favorites WHERE id = 'f1'").fetchone()
    finally:
        conn.close()
    assert row == (0,)


def test_migration_head_includes_the_fase_11_scheduled_download_columns(tmp_path: Path):
    db_path = tmp_path / "migrated.db"
    _run_alembic("upgrade", "head", db_path=db_path)

    conn = sqlite3.connect(db_path)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(scheduled_downloads)")}
    finally:
        conn.close()

    assert {
        "run_at",
        "weekdays",
        "window_seconds",
        "priority",
        "max_attempts",
        "download_directory",
        "preferred_format",
        "next_due_at",
        "attempts",
        "download_id",
        "last_outcome",
    } <= columns


def test_upgrading_with_pre_existing_scheduled_downloads_data_does_not_fail(tmp_path: Path):
    """Same lesson as the favorites regression test: every FASE 11 column is
    NOT NULL with a server_default, so this must not fail against a database
    that already has scheduled_downloads rows from before the migration."""
    db_path = tmp_path / "migrated.db"
    _run_alembic("upgrade", "b34855f71713", db_path=db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO scheduled_downloads "
            "(id, channel_platform, channel_external_id, trigger, quality_preference, "
            "is_active, created_at) VALUES "
            "('s1', 'twitch', '123', 'recurring', 'best', 1, '2026-01-01 00:00:00')"
        )
        conn.commit()
    finally:
        conn.close()

    _run_alembic("upgrade", "head", db_path=db_path)  # must not raise

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT weekdays, window_seconds, priority, max_attempts, attempts "
            "FROM scheduled_downloads WHERE id = 's1'"
        ).fetchone()
    finally:
        conn.close()
    assert row == ("", 14400, 0, 3, 0)


def test_downgrading_the_fase_11_migration_removes_only_its_own_columns(tmp_path: Path):
    db_path = tmp_path / "migrated.db"
    _run_alembic("upgrade", "head", db_path=db_path)

    _run_alembic("downgrade", "b34855f71713", db_path=db_path)

    conn = sqlite3.connect(db_path)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(scheduled_downloads)")}
    finally:
        conn.close()
    assert "run_at" not in columns
    assert {"id", "channel_platform", "trigger", "is_active"} <= columns  # older columns intact


# --- FASE 13: settings table ------------------------------------------------


def test_migration_head_includes_the_fase_13_settings_table(tmp_path: Path):
    db_path = tmp_path / "migrated.db"
    _run_alembic("upgrade", "head", db_path=db_path)

    conn = sqlite3.connect(db_path)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(settings)")}
    finally:
        conn.close()

    assert {
        "id", "language", "minimize_to_tray", "default_directory",
        "default_quality_preference", "default_format", "max_concurrent_downloads",
        "retry_max_attempts", "retry_base_delay_seconds", "retry_max_delay_seconds",
        "notifications_enabled", "theme", "temp_directory",
        "live_monitor_poll_interval_seconds",
    } <= columns  # fmt: skip


async def test_a_real_migrated_database_round_trips_settings_through_the_real_repository(
    tmp_path: Path,
):
    from twick_hub.domain.enums import Theme
    from twick_hub.domain.settings import Settings
    from twick_hub.infrastructure.persistence.settings_repository import SqlSettingsRepository

    db_path = tmp_path / "migrated.db"
    _run_alembic("upgrade", "head", db_path=db_path)
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    repo = SqlSettingsRepository(session_factory)

    assert await repo.get() == Settings()  # no row yet: defaults

    changed = Settings().updated(theme=Theme.DARK, max_concurrent_downloads=8)
    await repo.save(changed)

    assert await repo.get() == changed


def test_downgrading_the_fase_13_migration_removes_only_the_settings_table(tmp_path: Path):
    db_path = tmp_path / "migrated.db"
    _run_alembic("upgrade", "head", db_path=db_path)

    _run_alembic("downgrade", "c81d3f7a9b20", db_path=db_path)

    tables = _tables_in(db_path)
    assert "settings" not in tables
    assert "scheduled_downloads" in tables  # everything else intact


# --- FASE 14: update_attempts table -----------------------------------------


def test_migration_head_includes_the_fase_14_update_attempts_table(tmp_path: Path):
    db_path = tmp_path / "migrated.db"
    _run_alembic("upgrade", "head", db_path=db_path)

    conn = sqlite3.connect(db_path)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(update_attempts)")}
    finally:
        conn.close()

    assert {
        "id", "from_version", "to_version", "download_url", "sha256", "status",
        "started_at", "finished_at", "artifact_path", "backup_path", "error_message",
    } <= columns  # fmt: skip


async def test_a_real_migrated_database_round_trips_an_update_attempt(tmp_path: Path):
    from twick_hub.domain.enums import UpdateStatus
    from twick_hub.domain.updates import UpdateAttempt
    from twick_hub.domain.version import Version
    from twick_hub.infrastructure.persistence.update_attempt_repository import (
        SqlUpdateAttemptRepository,
    )

    db_path = tmp_path / "migrated.db"
    _run_alembic("upgrade", "head", db_path=db_path)
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    repo = SqlUpdateAttemptRepository(session_factory)

    attempt = UpdateAttempt(
        from_version=Version.parse("1.0.0"),
        to_version=Version.parse("1.1.0"),
        download_url="https://example.invalid/u.zip",
        sha256="f" * 64,
        status=UpdateStatus.READY_TO_INSTALL,
    )
    await repo.save(attempt)

    assert await repo.get(attempt.id) == attempt


def test_downgrading_the_fase_14_migration_removes_only_the_update_attempts_table(tmp_path: Path):
    db_path = tmp_path / "migrated.db"
    _run_alembic("upgrade", "head", db_path=db_path)

    _run_alembic("downgrade", "d4e9f2a1c8b3", db_path=db_path)

    tables = _tables_in(db_path)
    assert "update_attempts" not in tables
    assert "settings" in tables  # everything else intact


# --- FASE 15: legacy_migration_runs table -----------------------------------


def test_migration_head_includes_the_fase_15_legacy_migration_runs_table(tmp_path: Path):
    db_path = tmp_path / "migrated.db"
    _run_alembic("upgrade", "head", db_path=db_path)

    conn = sqlite3.connect(db_path)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(legacy_migration_runs)")}
    finally:
        conn.close()

    assert {
        "id", "source_path", "source_sha256", "backup_path", "status",
        "started_at", "finished_at", "settings_migrated", "previous_settings_json",
        "account_token_migrated", "created_favorite_ids", "created_scheduled_download_ids",
        "created_download_ids", "skipped_bookmark_logins",
        "skipped_scheduled_download_logins", "warnings", "error_message",
    } <= columns  # fmt: skip


async def test_a_real_migrated_database_round_trips_a_legacy_migration_run(tmp_path: Path):
    from twick_hub.domain.enums import LegacyMigrationStatus
    from twick_hub.domain.migration import LegacyMigrationRun
    from twick_hub.infrastructure.persistence.legacy_migration_run_repository import (
        SqlLegacyMigrationRunRepository,
    )

    db_path = tmp_path / "migrated.db"
    _run_alembic("upgrade", "head", db_path=db_path)
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    repo = SqlLegacyMigrationRunRepository(session_factory)

    run = LegacyMigrationRun(
        source_path="/legacy/settings.json",
        source_sha256="a" * 64,
        backup_path="/backups/settings.json.bak",
        status=LegacyMigrationStatus.COMPLETED_WITH_WARNINGS,
        created_favorite_ids=("f1", "f2"),
        warnings=("a warning",),
    )
    await repo.save(run)

    assert await repo.get(run.id) == run
    assert await repo.find_by_source_hash("a" * 64) == run


def test_downgrading_the_fase_15_migration_removes_only_the_legacy_migration_runs_table(
    tmp_path: Path,
):
    db_path = tmp_path / "migrated.db"
    _run_alembic("upgrade", "head", db_path=db_path)

    _run_alembic("downgrade", "e7a2b8c4f610", db_path=db_path)

    tables = _tables_in(db_path)
    assert "legacy_migration_runs" not in tables
    assert "update_attempts" in tables  # everything else intact
