"""Kick live status for many channels at once — implements
``domain.protocols.BatchLiveStatusProvider``, the backend of Kick's polling
live monitor (docs/architecture-decisions.md AD-06).

One ``GET /livestreams`` covers up to 50 broadcasters
(docs/kick-audit.md), so N favorites cost ``ceil(N / 50)`` requests per
poll instead of N.
"""

from __future__ import annotations

from collections.abc import Sequence

from twick_hub.domain.content import Stream
from twick_hub.domain.enums import Platform
from twick_hub.domain.monitoring import LiveStatusBatch
from twick_hub.domain.value_objects import PlatformRef
from twick_hub.infrastructure.kick.client import KickAPIClient
from twick_hub.infrastructure.kick.errors import KickAPIError
from twick_hub.infrastructure.kick.mappers import map_live_stream

MAX_IDS_PER_REQUEST = 50


class KickBatchLiveStatusProvider:
    def __init__(self, client: KickAPIClient) -> None:
        self._client = client

    async def get_live_streams(self, channel_refs: Sequence[PlatformRef]) -> LiveStatusBatch:
        wanted: dict[PlatformRef, None] = {}
        for ref in channel_refs:
            if ref.platform is not Platform.KICK:
                raise ValueError(f"not a Kick channel: {ref}")
            wanted[ref] = None
        ids = [ref.external_id for ref in wanted]

        live: dict[PlatformRef, Stream] = {}
        requests_made = 0
        for start in range(0, len(ids), MAX_IDS_PER_REQUEST):
            chunk = ids[start : start + MAX_IDS_PER_REQUEST]
            items = await self._client.get_livestreams(chunk)
            requests_made += 1
            for item in items:
                try:
                    stream = map_live_stream(item)
                except (KeyError, ValueError, TypeError) as exc:
                    # Never skip-and-continue: a dropped item would read as
                    # "went offline". Fail the whole batch; the monitor
                    # keeps its previous state and backs off.
                    raise KickAPIError(f"unparseable /livestreams item: {exc!r}") from exc
                if stream.channel_ref in wanted:  # ignore anything we didn't ask about
                    live[stream.channel_ref] = stream
        return LiveStatusBatch(live=live, requests_made=requests_made)
