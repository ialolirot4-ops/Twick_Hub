"""Parses an HLS *media* playlist — the per-quality ``.m3u8`` that
``TwitchPlaybackResolver``/``PlaybackResolver.resolve()`` (FASE 4c) hands
back as ``PlaybackSource.url``, listing the actual ``.ts`` segments to
download. Deliberately separate from
``infrastructure/twitch/playback/manifest.py``'s master/variant-playlist
parser (Master Plan §16: "El parser HLS/M3U8 del original es
infraestructura técnica. No confundirlo con la nueva feature de Playlists
del usuario" — and picking one quality variant is FASE 4c's job, not
this module's).

A VOD/clip media playlist lists every segment up front and ends with
``#EXT-X-ENDLIST``. A live stream's playlist is a sliding window — older
segments roll off as new ones appear, and it never ends — so
``HlsPlaylistReader.poll_until_complete`` keeps re-reading it until either
``#EXT-X-ENDLIST`` shows up (the stream ended) or the caller cancels.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx


@dataclass(frozen=True, slots=True)
class HlsSegment:
    """One ``.ts`` chunk. ``sequence`` is HLS's own ``#EXT-X-MEDIA-SEQUENCE``-
    derived index, not just position in this particular playlist read — a
    live playlist's segment 0 today may be segment 40 by the next poll, so
    ``sequence`` is what ``SegmentManager`` uses to dedupe across polls.
    """

    sequence: int
    url: str
    duration_seconds: float


def parse_media_playlist(playlist: str, base_url: str) -> tuple[list[HlsSegment], bool]:
    """Returns ``(segments, is_complete)``. ``is_complete`` mirrors
    ``#EXT-X-ENDLIST``: ``True`` for a VOD/clip playlist that lists every
    segment up front, ``False`` for a live playlist that
    ``HlsPlaylistReader`` must re-read as the stream keeps producing new
    segments. Unrecognized tags (ad discontinuities, Twitch-specific
    metadata, ...) are ignored rather than rejected — this parser only
    needs segment URIs, their duration, and the end marker.
    """
    segments: list[HlsSegment] = []
    sequence = 0
    pending_duration = 0.0
    is_complete = False

    for raw_line in playlist.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#EXT-X-MEDIA-SEQUENCE:"):
            sequence = int(line.split(":", 1)[1])
            continue
        if line == "#EXT-X-ENDLIST":
            is_complete = True
            continue
        if line.startswith("#EXTINF:"):
            pending_duration = float(line[len("#EXTINF:") :].split(",", 1)[0])
            continue
        if line.startswith("#"):
            continue
        segments.append(
            HlsSegment(
                sequence=sequence, url=urljoin(base_url, line), duration_seconds=pending_duration
            )
        )
        sequence += 1
        pending_duration = 0.0

    return segments, is_complete


class HlsPlaylistReader:
    """Fetches and parses one media playlist. Constructed once per job
    with the ``httpx.AsyncClient`` FASE 4c's own adapters already use —
    matches the rest of Infrastructure rather than wrapping httpx behind
    a bespoke protocol.
    """

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._http = http_client

    async def read(self, playlist_url: str) -> tuple[list[HlsSegment], bool]:
        response = await self._http.get(playlist_url)
        response.raise_for_status()
        return parse_media_playlist(response.text, base_url=playlist_url)

    async def poll_until_complete(
        self,
        playlist_url: str,
        *,
        poll_interval_seconds: float = 5.0,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> AsyncIterator[list[HlsSegment]]:
        """Yields newly-seen segments each time the playlist grows, until
        ``#EXT-X-ENDLIST`` appears or ``should_stop()`` returns ``True``
        (checked between polls — cancellation/pause is cooperative, same
        as ``SegmentManager``). For a VOD/clip playlist this yields once
        and returns immediately, since ``is_complete`` is already ``True``
        on the first read.
        """
        _sleep = sleep or asyncio.sleep
        seen_sequences: set[int] = set()

        while True:
            segments, is_complete = await self.read(playlist_url)
            new_segments = [s for s in segments if s.sequence not in seen_sequences]
            seen_sequences.update(s.sequence for s in new_segments)
            if new_segments:
                yield new_segments
            if is_complete:
                return
            if should_stop is not None and should_stop():
                return
            await _sleep(poll_interval_seconds)
