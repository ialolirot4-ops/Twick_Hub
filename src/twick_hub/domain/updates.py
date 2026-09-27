"""Update-checking entities (Master Plan §51, FASE 14).

``UpdateInfo`` only ever exists *after* origin and integrity have been
verified (docs/architecture-decisions.md's FASE 14 entry) — there is no
"unverified manifest" type here on purpose. A source that hasn't checked
the signature yet has nothing to hand back except an error; by the time
application code holds an ``UpdateInfo``, "verificar origen" already
happened. Integrity (the artifact's own SHA-256) is checked separately,
once the artifact bytes exist — ``UpdateInfo.sha256`` is what that check
compares against, not proof of anything by itself.

``UpdateAttempt`` is the persisted record of one check-download-install
cycle — the same "an entity is a value with an id and a status," never
just an in-memory result, that ``Download`` already established (FASE 7),
here for the same reason: "verificar ... errores; rollback cuando sea
viable" (§51) needs something to inspect after the fact, possibly after a
restart.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from uuid import uuid4

from twick_hub.domain.enums import UpdateStatus
from twick_hub.domain.version import Version


class UpdateOriginError(Exception):
    """The manifest didn't come from a trusted origin — wrong host, or a
    signature that doesn't verify against the app's own trusted public
    key. Never a value to fall back from; always fatal to the check."""


class UpdateIntegrityError(Exception):
    """A downloaded artifact's SHA-256 didn't match ``UpdateInfo.sha256``."""


class DownloadsInProgressError(Exception):
    """Installing now would interrupt the user's own in-flight downloads
    (Master Plan §51: "No interferir con descargas activas"). Not a
    failure — the caller should retry once they've finished."""


@dataclass(frozen=True, slots=True)
class UpdateInfo:
    """A manifest whose origin and signature have already been verified
    (see this module's docstring) — never constructed from raw,
    unverified network input."""

    version: Version
    download_url: str
    sha256: str  # lowercase hex, 64 chars
    size_bytes: int
    release_notes: str | None = None
    published_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.download_url.startswith("https://"):
            raise ValueError("download_url must be https")
        digest = self.sha256.lower()
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("sha256 must be a 64-character hex digest")
        object.__setattr__(self, "sha256", digest)
        if self.size_bytes <= 0:
            raise ValueError("size_bytes must be positive")


@dataclass(frozen=True, slots=True)
class UpdateAttempt:
    from_version: Version
    to_version: Version
    download_url: str
    sha256: str
    status: UpdateStatus = UpdateStatus.AVAILABLE
    id: str = field(default_factory=lambda: uuid4().hex)
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime | None = None
    artifact_path: str | None = None  # where the verified download landed
    backup_path: str | None = None  # the pre-install backup, for rollback
    error_message: str | None = None

    def advanced(self, status: UpdateStatus, *, now: datetime, **fields: object) -> UpdateAttempt:
        """Pure transition helper, same shape as
        ``ScheduledDownload.begin_attempt``/``.finish`` (FASE 11):
        terminal statuses stamp ``finished_at``, everything else doesn't.
        """
        terminal = status in (UpdateStatus.INSTALLED, UpdateStatus.FAILED, UpdateStatus.ROLLED_BACK)
        return replace(
            self, status=status, finished_at=now if terminal else self.finished_at, **fields
        )
