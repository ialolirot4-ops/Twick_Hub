"""Application configuration.

A single, explicit ``AppConfig`` object is built once at startup (see
``bootstrap/dependencies.py``) and passed to whatever needs it. Nothing in
this codebase reads configuration through a global/import-time singleton —
see docs/architecture-decisions.md AD-03, which replaces TwitchLink 3.5.5's
``App.Instance`` pattern with explicit construction and injection.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def default_data_dir() -> Path:
    """Per-OS application data directory.

    Windows is the only confirmed packaging target so far
    (docs/architecture-decisions.md AD-10); macOS/Linux paths are provided
    so the skeleton isn't Windows-only at the code level, without that
    implying either platform is a supported target yet — FASE 19 decides
    that.
    """
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
    return Path(base) / "TwitchLinkNext"


class AppConfig(BaseSettings):
    """Loaded from ``TWITCHLINK_NEXT_*`` environment variables or a
    ``.env`` file in the working directory. Every field has a safe
    default so the skeleton runs with zero configuration.
    """

    model_config = SettingsConfigDict(
        env_prefix="TWITCHLINK_NEXT_",
        env_file=".env",
        extra="ignore",
    )

    app_name: str = "TwitchLink Next"
    data_dir: Path = Field(default_factory=default_data_dir)
    log_level: str = "INFO"
    database_url: str | None = None

    def resolved_database_url(self) -> str:
        """Returns ``database_url`` if set, otherwise a SQLite file under
        ``data_dir`` (created if missing). FASE 8 replaces the direct
        SQLite path with the real Alembic-managed schema; this skeleton
        only proves the plumbing works end to end.
        """
        if self.database_url:
            return self.database_url
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{self.data_dir / 'twitchlink_next.db'}"


def load_config() -> AppConfig:
    return AppConfig()
