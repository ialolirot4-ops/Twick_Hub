"""Download entities.

Split in two layers on purpose:

- :class:`Download` is the durable, user-facing record — what the
  Downloads and History pages (FASE 2) show. It has exactly the fields a
  screen needs: status, progress, where the file went.
- :class:`DownloadJob` and :class:`DownloadSegment` are the execution
  units the download engine (FASE 7 — DownloadService, DownloadExecutor,
  SegmentManager per docs/architecture-decisions.md) will actually work
  with. A Download can outlive several DownloadJob attempts (retries)
  without the UI-facing record needing to know about any of them
  individually.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from twick_hub.domain.enums import DownloadStatus, SegmentStatus
from twick_hub.domain.value_objects import Media


@dataclass(frozen=True, slots=True)
class Download:
    media: Media
    destination_path: str
    quality_label: str
    status: DownloadStatus = DownloadStatus.QUEUED
    progress_percent: float = 0.0
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    file_size_bytes: int | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.progress_percent <= 100.0:
            raise ValueError("progress_percent must be between 0 and 100")


@dataclass(frozen=True, slots=True)
class DownloadSegment:
    sequence_index: int
    url: str
    status: SegmentStatus = SegmentStatus.PENDING
    id: str = field(default_factory=lambda: uuid4().hex)
    byte_size: int | None = None


@dataclass(frozen=True, slots=True)
class DownloadJob:
    """One execution attempt at fulfilling a :class:`Download`."""

    download_id: str
    segments: tuple[DownloadSegment, ...] = ()
    attempt_number: int = 1
    id: str = field(default_factory=lambda: uuid4().hex)
    started_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        if self.attempt_number < 1:
            raise ValueError("attempt_number must be at least 1")
