"""SQLAlchemy-backed ``ChannelRepository``. Every public method is async
(the domain Protocol requires it) but delegates to a private sync method
run via ``asyncio.to_thread`` — Container's ``session_factory`` is sync
SQLAlchemy (docs/architecture-decisions.md's FASE 8 entry explains why:
FASE 1 already built it that way, and ``Application._shutdown()`` already
calls ``engine.dispose()`` synchronously), so this is what keeps a
blocking DB call from blocking the Qt/asyncio event loop without
reworking that already-working shutdown path.
"""

from __future__ import annotations

import asyncio

from sqlalchemy.orm import sessionmaker

from twick_hub.domain.identity import Channel
from twick_hub.domain.value_objects import PlatformRef
from twick_hub.infrastructure.persistence.mappers import channel_to_row, row_to_channel
from twick_hub.infrastructure.persistence.models import ChannelRow


class SqlChannelRepository:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    async def get(self, ref: PlatformRef) -> Channel | None:
        return await asyncio.to_thread(self._get_sync, ref)

    def _get_sync(self, ref: PlatformRef) -> Channel | None:
        with self._session_factory() as session:
            row = session.get(ChannelRow, (ref.platform.value, ref.external_id))
            return row_to_channel(row) if row is not None else None

    async def save(self, channel: Channel) -> None:
        await asyncio.to_thread(self._save_sync, channel)

    def _save_sync(self, channel: Channel) -> None:
        with self._session_factory() as session:
            session.merge(channel_to_row(channel))
            session.commit()
