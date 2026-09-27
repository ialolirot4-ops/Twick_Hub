"""Twitch live status for many channels at once — implements
``domain.protocols.BatchLiveStatusProvider``. This is the low-cost
fallback docs/risk-register.md RISK-TWITCH-01 promised for favorites
beyond EventSub's 5-channel budget, and the slow "reconcile" check behind
the channels EventSub *does* cover (application/live_monitor/hybrid_monitor.py).

Helix ``GET /streams`` takes up to 100 ``user_id`` values (repeated key)
and returns only the ones currently live. Response fields (``id``,
``user_id``, ``title``, ``game_name``, ``type``, ``viewer_count``,
``started_at``, ``thumbnail_url``) and the 429 behaviour (wait until the
epoch in ``Ratelimit-Reset``) are per Twitch's own API reference and
guide, cross-checked against two client libraries' typed models during
FASE 10.

**Unverified live:** like ``TwitchEventSubProvider`` (FASE 4d), this calls
Helix with the web client id and the user's browser-session token
(``WEB_CLIENT_ID``). Twitch isn't reachable from this project's sandbox,
so whether Helix accepts that pairing is PENDING real-account validation.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from datetime import datetime

import httpx

from twick_hub.domain.content import Stream
from twick_hub.domain.enums import Platform
from twick_hub.domain.errors import RateLimitedError
from twick_hub.domain.monitoring import LiveStatusBatch
from twick_hub.domain.value_objects import PlatformRef
from twick_hub.infrastructure.twitch.config import WEB_CLIENT_ID

STREAMS_URL = "https://api.twitch.tv/helix/streams"
MAX_IDS_PER_REQUEST = 100
# Helix returns thumbnails as a template; this is just a preview size.
_THUMBNAIL_SIZE = ("440", "248")


class TwitchHelixError(Exception):
    """Helix answered with an error status other than 429."""


class TwitchRateLimitedError(TwitchHelixError, RateLimitedError):
    """Helix answered 429. ``retry_after`` comes from ``Ratelimit-Reset``
    (a Unix epoch), converted to seconds from now."""


class TwitchBatchLiveStatusProvider:
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        user_token_getter: Callable[[], str],
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._http = http_client
        self._get_user_token = user_token_getter
        self._clock = clock

    async def get_live_streams(self, channel_refs: Sequence[PlatformRef]) -> LiveStatusBatch:
        wanted: dict[PlatformRef, None] = {}
        for ref in channel_refs:
            if ref.platform is not Platform.TWITCH:
                raise ValueError(f"not a Twitch channel: {ref}")
            wanted[ref] = None
        ids = [ref.external_id for ref in wanted]

        live: dict[PlatformRef, Stream] = {}
        requests_made = 0
        for start in range(0, len(ids), MAX_IDS_PER_REQUEST):
            chunk = ids[start : start + MAX_IDS_PER_REQUEST]
            response = await self._http.get(
                STREAMS_URL,
                params={"user_id": chunk, "first": str(MAX_IDS_PER_REQUEST)},
                headers={
                    "Client-Id": WEB_CLIENT_ID,
                    "Authorization": f"Bearer {self._get_user_token()}",
                },
            )
            requests_made += 1
            self._raise_for_status(response)
            for item in response.json().get("data") or []:
                if item.get("type") != "live":  # "" means an error state, not a live stream
                    continue
                stream = map_helix_stream(item)
                if stream.channel_ref in wanted:
                    live[stream.channel_ref] = stream
        return LiveStatusBatch(live=live, requests_made=requests_made)

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code == 429:
            raise TwitchRateLimitedError(
                f"Helix /streams returned 429: {response.text}",
                retry_after=self._seconds_until_reset(response),
            )
        if response.status_code >= 400:
            raise TwitchHelixError(
                f"Helix /streams returned {response.status_code}: {response.text}"
            )

    def _seconds_until_reset(self, response: httpx.Response) -> float | None:
        raw = response.headers.get("ratelimit-reset")
        if raw is None:
            return None
        try:
            return max(0.0, float(raw) - self._clock())
        except ValueError:
            return None


def map_helix_stream(data: dict) -> Stream:
    """Same domain ``Stream`` the GQL path produces
    (``gql/mappers.map_stream``): ``ref`` is the stream's own id,
    ``channel_ref`` the broadcaster's user id."""
    thumbnail = data.get("thumbnail_url") or None
    if thumbnail:
        thumbnail = thumbnail.replace("{width}", _THUMBNAIL_SIZE[0]).replace(
            "{height}", _THUMBNAIL_SIZE[1]
        )
    return Stream(
        ref=PlatformRef(platform=Platform.TWITCH, external_id=str(data["id"])),
        channel_ref=PlatformRef(platform=Platform.TWITCH, external_id=str(data["user_id"])),
        title=data.get("title") or "",
        category=data.get("game_name") or None,
        started_at=datetime.fromisoformat(data["started_at"]),
        viewer_count=data.get("viewer_count") or 0,
        thumbnail_url=thumbnail,
    )
