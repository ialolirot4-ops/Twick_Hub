"""FASE 18 — Testing: ``_RealWebSocketConnection`` had zero coverage
beyond the module importing cleanly — ``connect_real`` itself needs a real
socket to Twitch's EventSub endpoint (unreachable from this sandbox, same
limitation as the rest of this package), but the thin wrapper class around
an already-open connection needs nothing Twitch-specific at all: any
object with async ``recv``/``close`` methods exercises it exactly like a
real ``websockets.ClientConnection`` would.
"""

from __future__ import annotations

import pytest

from twick_hub.infrastructure.twitch.eventsub.connection import _RealWebSocketConnection


class _FakeRawConnection:
    def __init__(self, messages: list) -> None:
        self._messages = list(messages)
        self.closed = False

    async def recv(self):
        return self._messages.pop(0)

    async def close(self) -> None:
        self.closed = True


async def test_recv_returns_the_underlying_text_frame():
    raw = _FakeRawConnection(["hello"])
    conn = _RealWebSocketConnection(raw)  # type: ignore[arg-type]

    assert await conn.recv() == "hello"


async def test_recv_asserts_the_frame_is_text_not_bytes():
    """EventSub only ever sends text frames — a binary frame here would
    mean something is badly wrong upstream, not a case to silently handle.
    """
    raw = _FakeRawConnection([b"binary-frame"])
    conn = _RealWebSocketConnection(raw)  # type: ignore[arg-type]

    with pytest.raises(AssertionError):
        await conn.recv()


async def test_close_delegates_to_the_underlying_connection():
    raw = _FakeRawConnection([])
    conn = _RealWebSocketConnection(raw)  # type: ignore[arg-type]

    await conn.close()

    assert raw.closed is True
