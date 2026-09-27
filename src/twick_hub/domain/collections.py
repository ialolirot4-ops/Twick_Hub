"""User-collection entities: things the person curates themselves —
favorites, playlists, and scheduled downloads.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from uuid import uuid4

from twick_hub.domain.enums import (
    MediaKind,
    Platform,
    ScheduleOutcome,
    SchedulePhase,
    ScheduleTrigger,
)
from twick_hub.domain.schedule_math import next_occurrence
from twick_hub.domain.value_objects import Duration, Media, PlatformRef


@dataclass(frozen=True, slots=True)
class Favorite:
    """Master Plan §21's new Favorite model. ``username``/``display_name``/
    ``avatar_url`` from §21 are deliberately NOT duplicated here — they're
    already ``Channel.user``'s job (fetched via ``ChannelRepository``), so
    a favorite only holds ``channel_ref``. ``notify_on_live``/
    ``auto_download`` keep their pre-existing names rather than renaming
    to §21's ``notification_enabled``/``auto_download_enabled`` — same
    concept, a pure rename brings no benefit. ``position`` isn't in §21's
    list but is what FASE 9's "reorder" function needs to actually
    persist an order across sessions.
    """

    channel_ref: PlatformRef
    notify_on_live: bool = True
    auto_download: bool = False
    preferred_quality: str | None = None
    preferred_format: str | None = None
    download_directory: str | None = None
    position: int = 0
    id: str = field(default_factory=lambda: uuid4().hex)
    added_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True, slots=True)
class PlaylistItem:
    media: Media
    position: int
    id: str = field(default_factory=lambda: uuid4().hex)
    added_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True, slots=True)
class Playlist:
    name: str
    items: tuple[PlaylistItem, ...] = ()
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: datetime = field(default_factory=datetime.now)

    def with_item_added(self, media: Media) -> Playlist:
        """Returns a new Playlist with ``media`` appended at the end.

        Entities here are immutable (see identity.py's module docstring),
        so "adding an item" is a pure function returning a new value
        rather than mutating ``items`` in place.
        """
        new_item = PlaylistItem(media=media, position=len(self.items))
        return replace(self, items=(*self.items, new_item))

    def renamed(self, name: str) -> Playlist:
        return replace(self, name=name)

    def with_item_removed(self, item_id: str) -> Playlist:
        """Removes the item and closes the gap in ``position`` so it stays
        a contiguous 0..n-1 sequence — the same invariant ``with_item_added``
        relies on (it appends at ``len(self.items)``).

        Raises ``ValueError`` rather than silently no-op'ing on an id that
        isn't there — the caller (``RemoveMediaFromPlaylistUseCase``) is in
        a better position to say "not found" than a swallowed no-op would
        be.
        """
        remaining = [item for item in self.items if item.id != item_id]
        if len(remaining) == len(self.items):
            raise ValueError(f"no item {item_id!r} in playlist {self.id!r}")
        renumbered = tuple(replace(item, position=i) for i, item in enumerate(remaining))
        return replace(self, items=renumbered)

    def with_items_reordered(self, item_ids: Sequence[str]) -> Playlist:
        """``item_ids`` is the *complete* new order, exactly like a
        drag-and-drop UI would compute client-side and send in one call —
        not a single from/to move, so there's one obviously-correct way to
        apply it and nothing to get subtly wrong about intermediate states.

        Raises ``ValueError`` if ``item_ids`` isn't a permutation of the
        playlist's current item ids (wrong length, a duplicate, an id from
        another playlist, or one missing) — reordering around a mismatch
        would silently drop or duplicate items.
        """
        current = {item.id: item for item in self.items}
        if len(item_ids) != len(current) or set(item_ids) != current.keys():
            raise ValueError("item_ids must be exactly a reordering of the playlist's own items")
        reordered = tuple(
            replace(current[item_id], position=i) for i, item_id in enumerate(item_ids)
        )
        return replace(self, items=reordered)

    def to_export_dict(self) -> dict:
        """A plain, JSON-serialisable snapshot — name and items only, no
        ids or timestamps, since those are meaningless (or actively
        confusing — a re-imported playlist is a new playlist with new
        ids) once re-imported into this or another library."""
        return {
            "name": self.name,
            "items": [_media_to_export_dict(item.media) for item in self.items],
        }

    @classmethod
    def from_export_dict(cls, data: dict, *, name: str | None = None) -> Playlist:
        """The inverse of ``to_export_dict``. ``name`` overrides the
        exported name (the caller may want "Copy of X", or the user may
        rename it on import) — the export's own name is used when omitted.
        Raises ``ValueError`` naming the problem for any malformed input
        rather than letting a ``KeyError``/``TypeError`` leak the internal
        shape of the export format to the caller.
        """
        try:
            playlist_name = name if name is not None else data["name"]
            raw_items = data["items"]
            playlist = cls(name=playlist_name)
            for raw_item in raw_items:
                playlist = playlist.with_item_added(_media_from_export_dict(raw_item))
            return playlist
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ValueError(f"malformed playlist export data: {exc}") from exc


def _media_to_export_dict(media: Media) -> dict:
    return {
        "kind": media.kind.value,
        "platform": media.ref.platform.value,
        "external_id": media.ref.external_id,
        "title": media.title,
        "channel_platform": media.channel_ref.platform.value if media.channel_ref else None,
        "channel_external_id": media.channel_ref.external_id if media.channel_ref else None,
        "thumbnail_url": media.thumbnail_url,
        "duration_seconds": media.duration.total_seconds if media.duration else None,
    }


def _media_from_export_dict(data: dict) -> Media:
    channel_ref = None
    if data.get("channel_platform") is not None:
        channel_ref = PlatformRef(
            platform=Platform(data["channel_platform"]), external_id=data["channel_external_id"]
        )
    duration_seconds = data.get("duration_seconds")
    duration = Duration(total_seconds=duration_seconds) if duration_seconds is not None else None
    return Media(
        kind=MediaKind(data["kind"]),
        ref=PlatformRef(platform=Platform(data["platform"]), external_id=data["external_id"]),
        title=data["title"],
        channel_ref=channel_ref,
        thumbnail_url=data.get("thumbnail_url"),
        duration=duration,
    )


@dataclass(frozen=True, slots=True)
class ScheduledDownload:
    """One scheduled recording (Master Plan §20). What each ``trigger``
    means is documented on ``ScheduleTrigger``.

    The FASE 3 fields are unchanged; everything below ``last_triggered_at``
    is FASE 11 and defaulted, so existing rows and callers keep working.
    ``next_due_at``, ``attempts``, ``download_id`` and ``last_outcome`` are
    the scheduler's *persisted* state — what restart recovery reads to know
    where each item was when the app last stopped.
    """

    channel_ref: PlatformRef
    trigger: ScheduleTrigger
    quality_preference: str = "best"
    is_active: bool = True
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: datetime = field(default_factory=datetime.now)
    last_triggered_at: datetime | None = None

    # AT_TIME only
    run_at: datetime | None = None
    weekdays: tuple[int, ...] = ()  # non-empty → repeats weekly at run_at's time of day
    window_seconds: int = 4 * 3600  # how long past a due time the channel may still be recorded
    # all triggers
    priority: int = 0  # lower runs first; ties keep arrival order
    max_attempts: int = 3
    download_directory: str | None = None
    preferred_format: str | None = None
    # scheduler state
    next_due_at: datetime | None = None
    attempts: int = 0
    download_id: str | None = None
    last_outcome: ScheduleOutcome | None = None

    def __post_init__(self) -> None:
        if self.trigger is ScheduleTrigger.AT_TIME:
            if self.run_at is None:
                raise ValueError("an AT_TIME scheduled download needs run_at")
        elif self.run_at is not None or self.weekdays:
            raise ValueError("run_at/weekdays only apply to AT_TIME")
        if any(day not in range(7) for day in self.weekdays):
            raise ValueError("weekdays must be within 0 (Monday) .. 6 (Sunday)")
        if self.window_seconds < 60:
            raise ValueError("window_seconds must be at least 60")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")

    # --- pure schedule logic --------------------------------------------

    @property
    def window(self) -> timedelta:
        return timedelta(seconds=self.window_seconds)

    def with_first_due(self, now: datetime) -> ScheduledDownload:
        """Sets ``next_due_at`` for a brand-new AT_TIME item. A repeating
        item created after today's due time but inside its window arms
        immediately instead of waiting a week."""
        if self.trigger is not ScheduleTrigger.AT_TIME or self.run_at is None:
            return self
        if not self.weekdays or self.run_at > now - self.window:
            return replace(self, next_due_at=self.run_at)
        return replace(
            self,
            next_due_at=next_occurrence(self.run_at.time(), self.weekdays, now - self.window),
        )

    def phase(self, now: datetime) -> SchedulePhase:
        if not self.is_active:
            return SchedulePhase.DISABLED
        if self.download_id is not None:
            return SchedulePhase.RUNNING
        if self.trigger is not ScheduleTrigger.AT_TIME or self.next_due_at is None:
            return SchedulePhase.WAITING_LIVE
        if now < self.next_due_at:
            return SchedulePhase.SCHEDULED
        if now < self.next_due_at + self.window:
            return SchedulePhase.WAITING_LIVE
        return SchedulePhase.EXPIRED

    def begin_attempt(self, download_id: str | None, now: datetime) -> ScheduledDownload:
        """An attempt was made; ``download_id`` is the recording it
        started (None if it failed before one existed)."""
        return replace(
            self,
            attempts=self.attempts + 1,
            download_id=download_id,
            last_triggered_at=now if download_id is not None else self.last_triggered_at,
        )

    def attempts_exhausted(self) -> bool:
        return self.attempts >= self.max_attempts

    def finish(self, outcome: ScheduleOutcome, now: datetime) -> ScheduledDownload:
        """Closes the current run with ``outcome``. One-shot triggers turn
        themselves off (keeping ``last_outcome`` as history); RECURRING and
        a repeating AT_TIME stay armed for their next run."""
        base = replace(self, attempts=0, download_id=None, last_outcome=outcome)
        if self.trigger is ScheduleTrigger.RECURRING:
            return base
        if self.trigger is ScheduleTrigger.AT_TIME and self.weekdays and self.next_due_at:
            after = max(self.next_due_at, now - self.window)
            assert self.run_at is not None
            return replace(
                base, next_due_at=next_occurrence(self.run_at.time(), self.weekdays, after)
            )
        return replace(base, is_active=False, next_due_at=None)
