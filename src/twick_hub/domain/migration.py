"""Legacy migration entities (Master Plan §52, FASE 15).

``LegacyMigrationRun`` is the persisted record of one detect-backup-read-
validate-transform-write-verify cycle over a TwitchLink 3.5.x
``settings.json`` — the same "an entity is a value with an id and a
status, never just an in-memory result" shape ``UpdateAttempt`` already
established in FASE 14, here for the same reason: a migration needs to
be inspectable after the fact (was anything migrated already? what
exactly?) and, per this module's own requirement ("migrador
reversible/idempotente"), undoable.

Nothing here imports the legacy codebase, PyQt6, or touches a file —
that is infrastructure/migration's job (FASE 15 entry in
docs/architecture-decisions.md). This module only knows the *shape* of
a migration outcome.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from uuid import uuid4

from twick_hub.domain.enums import LegacyMigrationStatus

_TERMINAL = frozenset(
    (
        LegacyMigrationStatus.COMPLETED,
        LegacyMigrationStatus.COMPLETED_WITH_WARNINGS,
        LegacyMigrationStatus.FAILED,
        LegacyMigrationStatus.ROLLED_BACK,
    )
)


@dataclass(frozen=True, slots=True)
class LegacyMigrationRun:
    """One run of the legacy migrator against one legacy ``settings.json``.

    ``source_sha256`` is the idempotency key (docs/architecture-
    decisions.md's FASE 15 entry): re-running the migrator against a
    byte-identical legacy file is a safe no-op that returns the existing
    run rather than re-importing anything, without needing to compare
    every migrated field one by one. ``previous_settings_json`` is a
    verbatim snapshot of whatever ``Settings`` row existed *before* this
    run touched it (``None`` if this run never touched Settings) — the
    only way to make an inherently-overwriting singleton row (FASE 13:
    one ``Settings`` row per installation) honestly reversible, since
    "restore the previous value" requires having kept it.
    """

    source_path: str
    source_sha256: str  # lowercase hex, sha256 of the legacy file's raw bytes
    backup_path: str
    status: LegacyMigrationStatus = LegacyMigrationStatus.RUNNING
    id: str = field(default_factory=lambda: uuid4().hex)
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime | None = None

    settings_migrated: bool = False
    previous_settings_json: str | None = None  # for rollback; see docstring above
    account_token_migrated: bool = False

    # Ids this run created, in the order created — exactly what rollback()
    # deletes. Deliberately not "everything migrated", since an item that
    # already existed (idempotent skip) must NOT be deleted by a rollback
    # of *this* run — it wasn't this run's to own.
    created_favorite_ids: tuple[str, ...] = ()
    created_scheduled_download_ids: tuple[str, ...] = ()
    created_download_ids: tuple[str, ...] = ()

    # Bookmark logins / scheduled-download channels that could not be
    # resolved to a real channel (no network, unknown login, platform
    # adapter absent) — Master Plan §0.7: recorded as skipped, never
    # silently dropped and never claimed as migrated.
    skipped_bookmark_logins: tuple[str, ...] = ()
    skipped_scheduled_download_logins: tuple[str, ...] = ()

    warnings: tuple[str, ...] = ()
    error_message: str | None = None

    def advanced(
        self, status: LegacyMigrationStatus, *, now: datetime, **fields: object
    ) -> LegacyMigrationRun:
        """Pure transition helper, same shape as
        ``UpdateAttempt.advanced``/``ScheduledDownload.finish``: terminal
        statuses stamp ``finished_at``, everything else doesn't."""
        terminal = status in _TERMINAL
        return replace(
            self, status=status, finished_at=now if terminal else self.finished_at, **fields
        )

    @property
    def is_terminal(self) -> bool:
        return self.status in _TERMINAL

    @property
    def total_items_created(self) -> int:
        return (
            len(self.created_favorite_ids)
            + len(self.created_scheduled_download_ids)
            + len(self.created_download_ids)
        )
