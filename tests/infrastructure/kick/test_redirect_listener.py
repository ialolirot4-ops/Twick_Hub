from __future__ import annotations

import asyncio

import httpx
import pytest

from twick_hub.infrastructure.kick.redirect_listener import LocalHttpRedirectListener


async def test_wait_for_callback_captures_code_and_state():
    listener = LocalHttpRedirectListener("127.0.0.1", 51900, "/callback")
    wait_task = asyncio.create_task(listener.wait_for_callback(timeout=5))
    await asyncio.sleep(0.2)  # let the server start listening

    async with httpx.AsyncClient() as client:
        response = await client.get(
            "http://127.0.0.1:51900/callback", params={"code": "abc123", "state": "xyz789"}
        )

    assert response.status_code == 200
    code, state = await wait_task
    assert code == "abc123"
    assert state == "xyz789"


async def test_wait_for_callback_ignores_requests_to_a_different_path():
    listener = LocalHttpRedirectListener("127.0.0.1", 51901, "/callback")
    wait_task = asyncio.create_task(listener.wait_for_callback(timeout=1))
    await asyncio.sleep(0.2)

    async with httpx.AsyncClient() as client:
        response = await client.get("http://127.0.0.1:51901/not-the-callback-path")

    assert response.status_code == 404
    with pytest.raises(TimeoutError):
        await wait_task


async def test_wait_for_callback_times_out_if_nothing_arrives():
    listener = LocalHttpRedirectListener("127.0.0.1", 51902, "/callback")
    with pytest.raises(TimeoutError):
        await listener.wait_for_callback(timeout=0.3)
