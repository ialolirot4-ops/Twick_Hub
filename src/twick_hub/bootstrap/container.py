"""The dependency container.

A plain, explicit data holder — not a service locator. Nothing in this
codebase does ``Container.instance().thing`` or reaches a dependency
through import-time global state. A ``Container`` is built exactly once
(``bootstrap/dependencies.py``) and passed by constructor to whatever
needs it.

This replaces TwitchLink 3.5.5's ``Core/App.py``, which creates
``Instance = App(...)`` — plus eight services hung off it
(``NetworkAccessManager``, ``TwitchGQL``, ``Translator``,
``NotificationManager``, ``ContentManager``, ``TempManager``,
``ImageLoader``, ``PartnerContentManager``) — as a side effect of
importing the module. See docs/architecture-decisions.md AD-03 and
docs/migration-map.md.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from twick_hub.config.settings import AppConfig


@dataclass(frozen=True, slots=True)
class Container:
    config: AppConfig
    engine: Engine
    session_factory: sessionmaker

    # FASE 3+ adds twitch_client, kick_client, download_service, and so
    # on here — each built in dependencies.py and added as a field,
    # never reached through import-time global state.
