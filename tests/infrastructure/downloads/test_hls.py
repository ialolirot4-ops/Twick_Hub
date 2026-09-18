from __future__ import annotations

import httpx
import pytest

from twick_hub.infrastructure.downloads.hls import HlsPlaylistReader, parse_media_playlist

_VOD_PLAYLIST = """
#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:10
#EXT-X-MEDIA-SEQUENCE:0
#EXTINF:9.009,
segment0.ts
#EXTINF:9.009,
segment1.ts
#EXT-X-ENDLIST
""".strip()

_LIVE_PLAYLIST_FIRST = """
#EXTM3U
#EXT-X-TARGETDURATION:10
#EXT-X-MEDIA-SEQUENCE:40
#EXTINF:10.000,
seg40.ts
#EXTINF:10.000,
seg41.ts
""".strip()

_LIVE_PLAYLIST_SECOND = """
#EXTM3U
#EXT-X-TARGETDURATION:10
#EXT-X-MEDIA-SEQUENCE:41
#EXTINF:10.000,
seg41.ts
#EXTINF:10.000,
seg42.ts
""".strip()

_LIVE_PLAYLIST_ENDED = """
#EXTM3U
#EXT-X-TARGETDURATION:10
#EXT-X-MEDIA-SEQUENCE:42
#EXTINF:10.000,
seg42.ts
#EXT-X-ENDLIST
""".strip()


def test_parse_vod_playlist_is_complete_with_all_segments():
    segments, is_complete = parse_media_playlist(_VOD_PLAYLIST, base_url="https://cdn.example/vod/index.m3u8")

    assert is_complete is True
    assert [s.sequence for s in segments] == [0, 1]
    assert segments[0].url == "https://cdn.example/vod/segment0.ts"
    assert segments[0].duration_seconds == pytest.approx(9.009)


def test_parse_live_playlist_is_not_complete():
    segments, is_complete = parse_media_playlist(_LIVE_PLAYLIST_FIRST, base_url="https://cdn.example/live/index.m3u8")

    assert is_complete is False
    assert [s.sequence for s in segments] == [40, 41]


def test_parse_resolves_relative_urls_against_playlist_base():
    segments, _ = parse_media_playlist(_VOD_PLAYLIST, base_url="https://cdn.example/vod/index.m3u8")
    assert all(s.url.startswith("https://cdn.example/vod/") for s in segments)


def test_parse_ignores_unrecognized_tags():
    playlist = "#EXTM3U\n#EXT-X-DISCONTINUITY\n#EXTINF:5.0,\nseg.ts\n#EXT-X-ENDLIST"
    segments, is_complete = parse_media_playlist(playlist, base_url="https://cdn.example/index.m3u8")
    assert is_complete is True
    assert len(segments) == 1


async def test_reader_read_fetches_and_parses():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_VOD_PLAYLIST)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    reader = HlsPlaylistReader(client)

    segments, is_complete = await reader.read("https://cdn.example/vod/index.m3u8")

    assert is_complete is True
    assert len(segments) == 2


async def test_reader_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    reader = HlsPlaylistReader(client)

    with pytest.raises(httpx.HTTPStatusError):
        await reader.read("https://cdn.example/vod/index.m3u8")


async def test_poll_until_complete_yields_once_for_vod():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_VOD_PLAYLIST)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    reader = HlsPlaylistReader(client)

    batches = [batch async for batch in reader.poll_until_complete("https://cdn.example/vod/index.m3u8")]

    assert len(batches) == 1
    assert [s.sequence for s in batches[0]] == [0, 1]


async def test_poll_until_complete_dedupes_across_polls_and_stops_at_endlist():
    responses = [_LIVE_PLAYLIST_FIRST, _LIVE_PLAYLIST_SECOND, _LIVE_PLAYLIST_ENDED]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=responses.pop(0))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    reader = HlsPlaylistReader(client)

    sleeps: list[float] = []

    async def instant_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    batches = [
        batch
        async for batch in reader.poll_until_complete(
            "https://cdn.example/live/index.m3u8", poll_interval_seconds=5.0, sleep=instant_sleep
        )
    ]

    # seg41 appears in both the first and second poll — must only surface once.
    all_sequences = [s.sequence for batch in batches for s in batch]
    assert all_sequences == [40, 41, 42]
    assert sleeps == [5.0, 5.0]


async def test_poll_until_complete_stops_when_should_stop_returns_true():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_LIVE_PLAYLIST_FIRST)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    reader = HlsPlaylistReader(client)

    async def instant_sleep(seconds: float) -> None:
        return None

    batches = [
        batch
        async for batch in reader.poll_until_complete(
            "https://cdn.example/live/index.m3u8", sleep=instant_sleep, should_stop=lambda: True
        )
    ]

    assert len(batches) == 1  # first read still yields its segments, then stops before re-polling
