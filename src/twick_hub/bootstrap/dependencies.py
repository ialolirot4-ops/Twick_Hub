"""Builds the ``Container`` exactly once, in the right order.

Importing this module has no side effects — nothing runs, no Qt object
is created, no database connection is opened, until ``build_container()``
is actually called. This is the point of docs/architecture-decisions.md
AD-03: TwitchLink 3.5.5's ``Core/App.py`` does the opposite, creating
``Instance = App(...)`` as a side effect of import.
"""

from __future__ import annotations

from twick_hub.bootstrap.container import Container
from twick_hub.config.settings import AppConfig, load_config
from twick_hub.infrastructure.persistence.engine import (
    build_engine,
    build_session_factory,
)
from twick_hub.logging_setup import configure_logging


def build_container(config: AppConfig | None = None) -> Container:
    resolved_config = config or load_config()
    configure_logging(resolved_config)

    engine = build_engine(resolved_config)
    session_factory = build_session_factory(engine)

    return Container(
        config=resolved_config,
        engine=engine,
        session_factory=session_factory,
    )
