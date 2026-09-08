"""Domain value objects.

Immutable (``frozen=True``), compared by value, no identity of their own.
No PySide6 — see enums.py's module docstring.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from twick_hub.domain.enums import MediaKind, Platform


@dataclass(frozen=True, slots=True)
class PlatformRef:
    """Identifies one thing (a channel, a video, a clip, ...) on one
    platform. Twitch and Kick each have their own ID scheme, so a bare
    string is never a safe identifier on its own — everything that comes
    from a platform is keyed by (platform, external_id) instead.
    """

    platform: Platform
    external_id: str

    def __post_init__(self) -> None:
        if not self.external_id:
            raise ValueError("external_id must not be empty")


@dataclass(frozen=True, slots=True)
class Duration:
    """A length of time, in whole seconds."""

    total_seconds: int

    def __post_init__(self) -> None:
        if self.total_seconds < 0:
            raise ValueError("total_seconds must not be negative")

    @property
    def formatted(self) -> str:
        hours, remainder = divmod(self.total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"


@dataclass(frozen=True, slots=True)
class Media:
    """A lightweight, polymorphic reference to "a piece of watchable
    content" — a stream, a video, or a clip — without pulling in the full
    entity. Download, Favorite, PlaylistItem, and Notification all point
    at content through a Media rather than embedding a Stream/Video/Clip
    directly, so they don't need to care which of the three it is.
    """

    kind: MediaKind
    ref: PlatformRef
    title: str
    channel_ref: PlatformRef | None = None
    thumbnail_url: str | None = None
    duration: Duration | None = None


@dataclass(frozen=True, slots=True)
class PlaybackSource:
    """One downloadable quality variant of a :class:`Media`, as resolved
    by a ``PlaybackResolver`` (domain/protocols.py). Deliberately doesn't
    know whether it came from Twitch's playback-access-token flow or
    Kick's — see docs/architecture-decisions.md AD-05/AD-04.
    """

    url: str
    quality_label: str
    bandwidth_bps: int | None = None


_TEMPLATE_TOKEN = re.compile(r"\{(\w+)\}")


@dataclass(frozen=True, slots=True)
class FilenameTemplate:
    """User-configurable output filename pattern (Settings page,
    docs/functional-baseline.md's "Custom filename templates"), e.g.
    ``"{channel}/{title} ({date})"``.
    """

    pattern: str

    def render(self, values: dict[str, str]) -> str:
        """Substitutes every ``{token}`` in the pattern from ``values``.

        Raises ``KeyError`` naming the missing token rather than silently
        leaving ``{token}`` in a filename or guessing a default — a
        half-rendered filename is worse than a clear error.
        """

        def _replace(match: re.Match[str]) -> str:
            token = match.group(1)
            if token not in values:
                raise KeyError(f"filename template references unknown token '{{{token}}}'")
            return values[token]

        return _TEMPLATE_TOKEN.sub(_replace, self.pattern)
