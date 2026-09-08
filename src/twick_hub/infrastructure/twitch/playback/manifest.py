"""Parses Twitch's HLS master playlist and orders the resulting
qualities. Ported from TwitchLink 3.5.5's ``VariantPlaylistReader`` +
``Resolution`` (Services/Playlist/): Twitch's master playlist uses
``#EXT-X-MEDIA`` tags followed by a bare URL on the next line, not the
more common ``#EXT-X-STREAM-INF`` + URL pattern — this parser matches
that specific, real shape rather than a generic HLS parser.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin

_TAG_RE = re.compile(r"^#(?P<name>[A-Z0-9-]+):(?P<attrs>.*)$")
_ATTR_RE = re.compile(r'([A-Z0-9-]+)=("(?:[^"]*)"|[^,]*)')
_RESOLUTION_RE = re.compile(r"(\d+)p(\d+(?:\.\d+)?)")


@dataclass(frozen=True, slots=True)
class VariantStream:
    name: str
    group_id: str
    url: str
    quality: int | None
    frame_rate: int | None

    @property
    def is_source(self) -> bool:
        return self.group_id == "chunked"

    @property
    def is_audio_only(self) -> bool:
        return self.group_id == "audio_only"

    @property
    def display_name(self) -> str:
        if self.quality is None or self.frame_rate is None:
            return self.name
        return f"{self.quality}p{self.frame_rate}"

    @property
    def sort_key(self) -> tuple[bool, int, int]:
        return (self.is_source, self.quality or 0, self.frame_rate or 0)


def _parse_attrs(raw: str) -> dict[str, str]:
    return {key: value.strip('"') for key, value in _ATTR_RE.findall(raw)}


def _parse_quality(group_id: str, name: str) -> tuple[int | None, int | None]:
    for text in (group_id, name):
        match = _RESOLUTION_RE.search(text)
        if match:
            quality = int(match.group(1))
            frame_rate = round(float(match.group(2)))
            return quality, frame_rate
    return None, None


def parse_variant_playlist(playlist: str, base_url: str) -> list[VariantStream]:
    """Returns every quality variant, sorted highest-first (source
    quality always wins regardless of its numeric resolution, then by
    resolution, then by frame rate — matches 3.5.5's ``Resolution``
    ordering exactly).
    """
    variants: list[VariantStream] = []
    pending_attrs: dict[str, str] | None = None

    for line in playlist.splitlines():
        line = line.strip()
        if not line:
            continue
        tag_match = _TAG_RE.match(line)
        if tag_match:
            if tag_match.group("name") == "EXT-X-MEDIA":
                pending_attrs = _parse_attrs(tag_match.group("attrs"))
            continue
        if pending_attrs is not None:
            group_id = pending_attrs.get("GROUP-ID", "")
            name = pending_attrs.get("NAME", "")
            quality, frame_rate = _parse_quality(group_id, name)
            variants.append(
                VariantStream(
                    name=name,
                    group_id=group_id,
                    url=urljoin(base_url, line),
                    quality=quality,
                    frame_rate=frame_rate,
                )
            )
            pending_attrs = None

    return sorted(variants, key=lambda variant: variant.sort_key, reverse=True)
