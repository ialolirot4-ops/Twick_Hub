"""WebSocket connection abstraction.

A narrow ``Protocol`` rather than depending on ``websockets`` types
directly, so tests can supply a fake connection that yields a scripted
sequence of messages — the same DI-for-testability pattern used
throughout this project (``IntegrityHeaderSource``, ``ChannelDirectory``,
``httpx.MockTransport``, ...). Twitch's real servers aren't reachable
from the sandbox this was built in regardless.
"""

from __future__ import annotations

from typing import Protocol

import websockets


class WebSocketConnection(Protocol):
    async def recv(self) -> str: ...

    async def close(self) -> None: ...


class _RealWebSocketConnection:
    """Thin wrapper matching ``WebSocketConnection`` exactly. Twitch's
    EventSub only ever sends text frames, so asserting ``str`` here is
    accurate, not just convenient — the underlying library's type is
    wider (``str | bytes``) because it supports binary WebSocket use
    generally, not because EventSub itself is ambiguous about it.
    """

    def __init__(self, connection: websockets.ClientConnection) -> None:
        self._connection = connection

    async def recv(self) -> str:
        data = await self._connection.recv()
        assert isinstance(data, str)
        return data

    async def close(self) -> None:
        await self._connection.close()


async def connect_real(url: str) -> WebSocketConnection:
    return _RealWebSocketConnection(await websockets.connect(url))
