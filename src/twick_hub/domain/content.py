"""Content entities: the three kinds of watchable/downloadable content a
channel can have. Each carries its own :class:`PlatformRef` (a Stream,
Video, or Clip is itself a distinct, identifiable thing on its platform,
separate from the Channel it belongs to).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from twick_hub.domain.identity import User
from twick_hub.domain.value_objects import Duration, PlatformRef


@dataclass(frozen=True, slots=True)
class Stream:
    """A currently-live broadcast."""

    ref: PlatformRef
    channel_ref: PlatformRef
    title: str
    category: str | None
    started_at: datetime
    viewer_count: int
    thumbnail_url: str | None = None


@dataclass(frozen=True, slots=True)
class Video:
    """A VOD (past broadcast, upload, or highlight).

    ``is_subscriber_only`` exists because it's one of TwitchLink 3.5.5's
    explicitly-required compatibility items
    (docs/functional-baseline.md) — a video a non-subscriber genuinely
    cannot download, not just a UI label.
    """

    ref: PlatformRef
    channel_ref: PlatformRef
    title: str
    published_at: datetime
    duration: Duration
    view_count: int
    is_subscriber_only: bool = False
    thumbnail_url: str | None = None


@dataclass(frozen=True, slots=True)
class Clip:
    """A short, user-created highlight from a stream or video."""

    ref: PlatformRef
    channel_ref: PlatformRef
    title: str
    creator: User
    created_at: datetime
    duration: Duration
    view_count: int
    thumbnail_url: str | None = None
