"""RISK-PKG-02: `ensure_schema_migrated` is the piece that was missing —
nothing in `src/twick_hub` ever created the schema on a real, fresh
install. `tests/infrastructure/persistence/test_migrations.py` already
proves the migration chain itself is correct (via the Alembic CLI, as a
subprocess, against a fresh SQLite file); these tests instead prove the
*in-process* call `main.py` actually makes — sharing a `Container`'s own
engine/connection, exactly like a real run — behaves the same way, and
that repositories can then be used with no manual
`Base.metadata.create_all()` anywhere, matching what a real user's first
launch needs.
"""

from __future__ import annotations

from sqlalchemy import inspect

from twick_hub.bootstrap.container import Container
from twick_hub.bootstrap.migrations import ensure_schema_migrated
from twick_hub.domain.enums import Platform
from twick_hub.domain.value_objects import PlatformRef

_EXPECTED_TABLES = {
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


def test_ensure_schema_migrated_creates_every_table_on_a_fresh_database(container: Container):
    assert inspect(container.engine).get_table_names() == []  # nothing yet — fresh file

    ensure_schema_migrated(container.engine)

    assert set(inspect(container.engine).get_table_names()) >= _EXPECTED_TABLES


def test_ensure_schema_migrated_is_safe_to_call_twice(container: Container):
    ensure_schema_migrated(container.engine)
    ensure_schema_migrated(container.engine)  # must not raise

    assert set(inspect(container.engine).get_table_names()) >= _EXPECTED_TABLES


async def test_a_container_can_be_used_with_no_manual_schema_setup(container: Container):
    """The exact scenario RISK-PKG-02 flagged: a real Container, a real
    (empty) file on disk, and no test-only `Base.metadata.create_all()`
    anywhere — only what `main.py` itself calls."""
    ensure_schema_migrated(container.engine)

    from twick_hub.domain.collections import Favorite

    favorite = Favorite(channel_ref=PlatformRef(platform=Platform.TWITCH, external_id="c1"))
    await container.favorites.save(favorite)

    assert await container.favorites.get_by_channel(favorite.channel_ref) == favorite


def test_ensure_schema_migrated_leaves_the_apps_logging_alone(container: Container):
    """FASE 21c: ``env.py`` used to call ``fileConfig(alembic.ini)`` even for
    this in-process run. ``fileConfig`` disables every logger that already
    exists (all of ``twick_hub``'s, created at import time) and resets the
    root level to WARNING — so after startup's migration the app's own
    logs, including ``TaskRunner``'s "Background UI task failed", vanished.
    Only the Alembic CLI (which never sets ``attributes["connection"]``)
    should get alembic.ini's logging setup.
    """
    import logging

    app_logger = logging.getLogger("twick_hub.bootstrap.application")
    root = logging.getLogger()
    level_before = root.level
    handlers_before = list(root.handlers)

    ensure_schema_migrated(container.engine)

    assert app_logger.disabled is False
    assert root.level == level_before
    assert root.handlers == handlers_before
