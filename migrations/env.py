from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from twick_hub.config.settings import load_config

# FASE 8: importing this registers every ORM table on Base.metadata —
# required before Alembic can autogenerate/compare against them. (Was
# deliberately absent through FASE 1-7, per this module's own prior
# comment: "no models exist yet — FASE 8 adds them.")
from twick_hub.infrastructure.persistence import models  # noqa: F401,E402
from twick_hub.infrastructure.persistence.base import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
# Twick Hub, FASE 21c: only for the CLI. ``fileConfig`` disables every
# logger that already exists and resets the root level to WARNING, which
# silenced the app's own logging after the in-process migration at startup
# (bootstrap/migrations.py sets ``attributes["connection"]``; the CLI never does).
if config.config_file_name is not None and config.attributes.get("connection") is None:
    fileConfig(config.config_file_name)

# Twick Hub: FASE 8 adds the real schema (see infrastructure/persistence/
# models.py) — target_metadata now reflects every table, not an
# intentionally empty one (that was FASE 1's proof-of-wiring only).
target_metadata = Base.metadata
config.set_main_option("sqlalchemy.url", load_config().resolved_database_url())

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    Twick Hub, FASE 21a (RISK-PKG-02): a caller running Alembic
    programmatically (bootstrap/migrations.py, not the CLI) shares its
    *own* already-open connection via ``config.attributes["connection"]``
    — the standard Alembic idiom for this — rather than this module
    opening a second connection from ``sqlalchemy.url`` above (which
    would silently point at the wrong database for an in-memory SQLite
    URL, and would ignore whatever ``AppConfig`` the caller actually
    built). The CLI (``alembic upgrade head``) never sets that
    attribute, so its behavior here is unchanged.
    """
    connectable = config.attributes.get("connection", None)
    if connectable is not None:
        context.configure(connection=connectable, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
        return

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
