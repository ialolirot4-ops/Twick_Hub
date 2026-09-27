from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
import pytest

from twick_hub.domain.updates import UpdateInfo, UpdateIntegrityError
from twick_hub.domain.version import Version
from twick_hub.infrastructure.updates.downloader import UpdateDownloader

_CONTENT = b"the update artifact bytes" * 100


def _info(content: bytes = _CONTENT, **overrides) -> UpdateInfo:
    fields = {
        "version": Version.parse("1.1.0"),
        "download_url": "https://example.invalid/update.zip",
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
    }
    return UpdateInfo(**{**fields, **overrides})


def _downloader(handler) -> UpdateDownloader:
    return UpdateDownloader(httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def test_downloads_and_verifies_a_correct_artifact(tmp_path: Path):
    handler = lambda request: httpx.Response(200, content=_CONTENT)  # noqa: E731
    destination = tmp_path / "artifact.zip"

    result = await _downloader(handler).download(_info(), destination)

    assert result == destination
    assert destination.read_bytes() == _CONTENT


async def test_a_checksum_mismatch_raises_and_removes_the_partial_file(tmp_path: Path):
    handler = lambda request: httpx.Response(200, content=b"different bytes entirely")  # noqa: E731
    destination = tmp_path / "artifact.zip"

    with pytest.raises(UpdateIntegrityError):
        await _downloader(handler).download(_info(), destination)

    assert not destination.exists()


async def test_an_http_error_raises_and_leaves_no_partial_file(tmp_path: Path):
    handler = lambda request: httpx.Response(404)  # noqa: E731
    destination = tmp_path / "artifact.zip"

    with pytest.raises(httpx.HTTPStatusError):
        await _downloader(handler).download(_info(), destination)

    assert not destination.exists()


async def test_creates_missing_parent_directories(tmp_path: Path):
    handler = lambda request: httpx.Response(200, content=_CONTENT)  # noqa: E731
    destination = tmp_path / "nested" / "dir" / "artifact.zip"

    await _downloader(handler).download(_info(), destination)

    assert destination.exists()


async def test_streams_in_chunks_rather_than_loading_everything_at_once(tmp_path: Path):
    """A weak proxy for "this streams": a large body still round-trips
    correctly and the destination file matches its hash — regardless of
    how many chunks httpx's mock transport happens to hand back."""
    big_content = b"x" * (3 * 1024 * 1024 + 17)  # not a clean multiple of the chunk size
    handler = lambda request: httpx.Response(200, content=big_content)  # noqa: E731
    destination = tmp_path / "artifact.zip"

    await _downloader(handler).download(_info(content=big_content), destination)

    assert destination.stat().st_size == len(big_content)
