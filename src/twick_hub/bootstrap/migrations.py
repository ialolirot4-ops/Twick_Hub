"""Upgrades a real database to the latest Alembic revision, in-process.

Deliberately **not** called from ``bootstrap/dependencies.py::build_container()``
itself — see docs/risk-register.md RISK-PKG-02 and
docs/architecture-decisions.md's FASE 21a follow-up entry for the full
reasoning. In short: ``build_container()`` is what nearly every test in
this suite calls, many of them against ``sqlite:///:memory:`` — a
database that only the one connection that created it can see, so a
second connection (which is what running Alembic would need) can't
reach it at all. Running migrations on every ``build_container()`` call
would either silently do nothing useful for those tests or be actively
wrong. ``main.py`` calls :func:`ensure_schema_migrated` itself, exactly
once, right after ``build_container()`` — the one call site that always
has a real, file-backed database and actually needs the schema to
exist.

Shares the engine's own connection with Alembic via
``config.attributes["connection"]`` (the standard Alembic idiom for
programmatic use — see ``migrations/env.py``'s matching branch) instead
of building a second engine from a re-derived URL, so this runs against
the *exact* database ``build_container()`` already opened, not
whatever ``AppConfig``/environment variables a fresh ``load_config()``
would produce.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

# repo root: src/twick_hub/bootstrap/migrations.py -> parents[3]. In a
# PyInstaller-frozen build this file lives inside the PYZ archive and
# this path does not resolve to a real directory — same limitation
# AD-97 already documents for QML before runtime_paths.py fixed it.
# alembic.ini/migrations/ aren't bundled by packaging/pyinstaller/
# twick_hub.spec yet (confirmed: its `datas` list only has the QML
# directory), so this only works in a source/editable install today.
# Left as a known gap for whoever next touches Packaging (FASE 19 is
# already closed BLOCKED for an unrelated reason — no Windows runner —
# so this doesn't regress anything a frozen build currently does).
_ALEMBIC_INI = Path(__file__).resolve().parents[3] / "alembic.ini"


def ensure_schema_migrated(engine: Engine) -> None:
    """Runs every pending migration up to ``head`` against ``engine``.

    Safe to call on a database that is already fully migrated (Alembic
    checks ``alembic_version`` and does nothing in that case) and,
    thanks to the migrations themselves already being written to tolerate
    pre-existing rows (see tests/infrastructure/persistence/test_migrations.py's
    "does_not_fail" regression tests), safe to call against a database
    with real data in it, not just an empty one.
    """
    config = Config(str(_ALEMBIC_INI))
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
