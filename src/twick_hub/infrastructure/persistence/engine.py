"""SQLAlchemy engine/session construction.

Built once in ``bootstrap/dependencies.py`` and stored on the
``Container`` — never created ad hoc inside a class that happens to need
a database connection. See docs/architecture-decisions.md AD-03.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import sessionmaker

from twick_hub.config.settings import AppConfig


def build_engine(config: AppConfig) -> Engine:
    return create_engine(config.resolved_database_url(), future=True)


def build_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
