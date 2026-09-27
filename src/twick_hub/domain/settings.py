"""Application-wide, user-editable Settings (Master Plan §50, FASE 13) —
General, Downloads, Notifications, Appearance, Storage, Advanced. "About"
is deliberately absent: it's static app/build metadata (version, license),
not something a user edits or a repository persists.

This is a *different* concept from ``config.settings.AppConfig``:
``AppConfig`` is process bootstrap configuration read from environment
variables before anything else starts (data directory, log level, the
database URL itself) — it has to exist before there's a database to read
a ``Settings`` row from. ``Settings`` is user preference *data*, edited
at runtime through the Settings page and persisted like any other entity
here (docs/architecture-decisions.md's FASE 8 entry deliberately deferred
the ``settings`` table until a real consumer existed — this is that
consumer).

One row per installation (a natural singleton, not a collection like
``Favorite``/``Playlist``) — ``SettingsRepository.get()`` always returns a
usable ``Settings`` (defaults, never ``None``), the same "runs with zero
configuration" philosophy ``AppConfig`` already follows.

Master Plan §50 lists these config knobs: directory, quality, format,
concurrency, retry, notifications, theme, language, minimized behavior,
platform options. Every field below maps to exactly one of those; "Twitch"
and "Kick" as separate config *sections* don't yet have anything genuinely
platform-specific to configure beyond what Downloads/Advanced already
cover (auth and cookie import are their own, later concern) — see
docs/architecture-decisions.md's FASE 13 entry for why those two sections
are deliberately left without dedicated fields rather than filled with
invented ones.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from twick_hub.domain.enums import Theme

#: The one row this application ever has. Not user-facing — nothing
#: constructs a ``Settings`` with a different id in normal use.
SETTINGS_ID = "default"


@dataclass(frozen=True, slots=True)
class Settings:
    id: str = SETTINGS_ID

    # --- General ---------------------------------------------------------
    language: str = "en"  # BCP-47 tag, e.g. "en", "es-MX"
    minimize_to_tray: bool = False

    # --- Downloads ---------------------------------------------------------
    default_directory: str | None = None
    default_quality_preference: str = "best"  # same vocabulary as
    #    application.scheduling.quality.select_quality: "best", "worst",
    #    "audio-only", an exact label, or a bare resolution like "720p".
    default_format: str | None = None  # None = each downloader's own default
    max_concurrent_downloads: int = 3  # DownloadCoordinator's worker_count
    retry_max_attempts: int = 3
    retry_base_delay_seconds: float = 1.0
    retry_max_delay_seconds: float = 30.0

    # --- Notifications -----------------------------------------------------
    notifications_enabled: bool = True  # master switch; per-favorite
    #    granularity is Favorite.notify_on_live, unaffected by this

    # --- Appearance --------------------------------------------------------
    theme: Theme = Theme.SYSTEM

    # --- Storage -----------------------------------------------------------
    temp_directory: str | None = None  # DownloadExecutor's work_dir; None =
    #    its own default (currently caller-supplied — see AD in FASE 13)

    # --- Advanced ----------------------------------------------------------
    #: Overrides application.live_monitor.polling_policy.PollingConfig's
    #: base_interval (docs/risk-register.md RISK-LIVE-02: the shipped
    #: default is an unproven starting point). None = use that default.
    live_monitor_poll_interval_seconds: float | None = None

    def __post_init__(self) -> None:
        if not self.language.strip():
            raise ValueError("language must not be empty")
        if not self.default_quality_preference.strip():
            raise ValueError("default_quality_preference must not be empty")
        if self.max_concurrent_downloads < 1:
            raise ValueError("max_concurrent_downloads must be at least 1")
        if self.retry_max_attempts < 1:
            raise ValueError("retry_max_attempts must be at least 1")
        if self.retry_base_delay_seconds < 0:
            raise ValueError("retry_base_delay_seconds must be >= 0")
        if self.retry_max_delay_seconds < self.retry_base_delay_seconds:
            raise ValueError("retry_max_delay_seconds must be >= retry_base_delay_seconds")
        if self.live_monitor_poll_interval_seconds is not None and (
            self.live_monitor_poll_interval_seconds <= 0
        ):
            raise ValueError("live_monitor_poll_interval_seconds must be > 0 when set")

    def updated(self, **fields: object) -> Settings:
        """``replace()`` under a name that reads naturally at the call
        site (``settings.updated(theme=Theme.DARK)``) — the same "pure,
        returns a new value" shape every other entity here uses."""
        return replace(self, **fields)

    def reset_to_defaults(self) -> Settings:
        """Matches the Settings page mock's "Reset to defaults" action —
        exactly what Master Plan §50 asks to be able to configure, put
        back to a known-good state in one step."""
        return Settings(id=self.id)
