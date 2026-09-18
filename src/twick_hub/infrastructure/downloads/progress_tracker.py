"""Tracks per-job download progress from segment counts — not bytes,
since segment count is what ``SegmentManager`` naturally knows without a
second progress signal to reconcile against ``ProgressTracker``.

A VOD/clip job knows its total segment count up front, so progress is a
plain 0-100 percentage. A live capture does not — the total only becomes
known once the stream ends — so ``start(job_id, total_segments=None)``
marks a job as "unbounded," and ``progress_of`` returns ``0.0`` for it
rather than a misleading number (see docs/architecture-decisions.md's
FASE 7 entry). ``segments_completed_of`` always works regardless of
whether the total is known, as an escape hatch for a future UI that wants
to show "N segments downloaded" instead of a percentage for live jobs.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ProgressTracker:
    _totals: dict[str, int | None] = field(default_factory=dict)
    _completed: dict[str, int] = field(default_factory=dict)

    def start(self, job_id: str, total_segments: int | None) -> None:
        self._totals[job_id] = total_segments
        self._completed[job_id] = 0

    def advance(self, job_id: str, by: int = 1) -> None:
        self._completed[job_id] = self._completed.get(job_id, 0) + by

    def progress_of(self, job_id: str) -> float:
        total = self._totals.get(job_id)
        if not total:
            return 0.0
        completed = self._completed.get(job_id, 0)
        return min(100.0, (completed / total) * 100.0)

    def segments_completed_of(self, job_id: str) -> int:
        return self._completed.get(job_id, 0)

    def finish(self, job_id: str) -> None:
        self._totals.pop(job_id, None)
        self._completed.pop(job_id, None)
