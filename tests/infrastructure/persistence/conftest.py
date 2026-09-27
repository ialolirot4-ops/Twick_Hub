from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Importing models registers every table on Base.metadata — required
# before create_all(), and otherwise unused directly in this file.
from twick_hub.infrastructure.persistence import models  # noqa: F401
from twick_hub.infrastructure.persistence.base import Base


@pytest.fixture
def session_factory() -> sessionmaker:
    # Every repository method runs its actual DB work on a worker thread
    # (asyncio.to_thread — see channel_repository.py's module docstring),
    # and a plain "sqlite:///:memory:" hands out a brand-new, empty
    # database per connection/thread. StaticPool + check_same_thread=False
    # is SQLAlchemy's documented fix: one shared connection for the whole
    # engine, safe here because tests are single-writer. The real engine
    # (infrastructure/persistence/engine.py) uses a file path, where this
    # doesn't apply.
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
