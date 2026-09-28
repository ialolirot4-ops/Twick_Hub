"""FASE 22.1 (RISK-ARCH-09): closing the app stops the download engine and
closes every ``httpx.AsyncClient`` *before* the database engine goes away.

Before this sub-phase ``Application._shutdown()`` only did
``engine.dispose()``: worker tasks were left pending on a loop that was
then closed, and both HTTP clients (the download engine's and the one
``build_platform_adapters()`` shares between Twitch and Kick) stayed open.
These tests drive the *real* ``Application`` and the *real* download
pipeline; only the network edge is faked, with ``httpx.MockTransport``.
"""

from __future__ import annotations

import asyncio
import dataclasses
from pathlib import Path

import httpx
from PySide6.QtCore import QTimer

import twick_hub.main as main_module
from twick_hub.application.platform_registry import PlatformAdapters
from twick_hub.bootstrap.application import Application
from twick_hub.bootstrap.container import Container
from twick_hub.bootstrap.dependencies import build_container
from twick_hub.bootstrap.migrations import ensure_schema_migrated
from twick_hub.config.settings import AppConfig
from twick_hub.domain.downloads import Download, DownloadJob
from twick_hub.domain.enums import MediaKind, Platform
from twick_hub.domain.value_objects import Media, PlatformRef, PlaybackSource
from twick_hub.presentation.qml_bridge.tasks import TaskRunner

_PLAYLIST = (
    "#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:10\n#EXT-X-MEDIA-SEQUENCE:0\n"
    "#EXTINF:10.0,\nseg0.ts\n#EXT-X-ENDLIST\n"
)


class _FakeTwitchPlaybackResolver:
    async def resolve(self, media, quality):
        return PlaybackSource(url="https://cdn.test/vod/index.m3u8", quality_label=quality)

    async def available_qualities(self, media) -> list[str]:
        return ["source"]


def _record_http_clients(monkeypatch, handler=None) -> list[httpx.AsyncClient]:
    """Makes every ``httpx.AsyncClient`` created from now on a recording
    subclass, optionally backed by a ``MockTransport`` so no request leaves
    the process. The list is what the test inspects after shutdown."""
    real_client = httpx.AsyncClient
    created: list[httpx.AsyncClient] = []

    class _RecordingClient(real_client):  # type: ignore[valid-type,misc]
        def __init__(self, *args, **kwargs) -> None:
            if handler is not None:
                kwargs.setdefault("transport", httpx.MockTransport(handler))
            super().__init__(*args, **kwargs)
            created.append(self)

    monkeypatch.setattr(httpx, "AsyncClient", _RecordingClient)
    return created


def _config(tmp_path: Path) -> AppConfig:
    # Kick credentials pinned to None: init kwargs win over the developer's
    # own TWICK_HUB_KICK_* environment variables, so the test is hermetic.
    return AppConfig(
        data_dir=tmp_path,
        database_url=f"sqlite:///{tmp_path}/shutdown.db",
        kick_client_id=None,
        kick_client_secret=None,
    )


def test_closing_the_app_mid_download_stops_the_workers_and_closes_the_client(
    tmp_path: Path, qapp, monkeypatch
):
    in_flight = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".m3u8"):
            return httpx.Response(200, text=_PLAYLIST)
        in_flight.set()  # a segment request arrived...
        await asyncio.sleep(3600)  # ...and never finishes
        raise AssertionError("unreachable: shutdown must cancel this request")

    clients = _record_http_clients(monkeypatch, handler)
    container = build_container(
        _config(tmp_path),
        platform_adapters={
            Platform.TWITCH: PlatformAdapters(playback_resolver=_FakeTwitchPlaybackResolver())
        },
    )
    ensure_schema_migrated(container.engine)
    media = Media(
        kind=MediaKind.VIDEO,
        ref=PlatformRef(platform=Platform.TWITCH, external_id="v1"),
        title="A VOD",
    )
    download = Download(
        media=media, destination_path=str(tmp_path / "out.mp4"), quality_label="source"
    )
    loops: list[asyncio.AbstractEventLoop] = []
    scenario_errors: list[BaseException] = []

    async def scenario() -> None:
        try:
            await container.downloads.save(download)
            await container.download_service.enqueue(DownloadJob(download_id=download.id))
            await asyncio.wait_for(in_flight.wait(), timeout=10)
        except BaseException as exc:  # noqa: BLE001 - reported below, never a hang
            scenario_errors.append(exc)
        finally:
            qapp.quit()

    def on_started() -> None:
        loop = asyncio.get_event_loop()  # the qasync loop Application.run() just installed
        loops.append(loop)
        loop.create_task(scenario())

    assert Application(container, qapp).run(on_started=on_started) == 0

    assert scenario_errors == []
    assert len(clients) == 1  # the download engine's client
    assert all(client.is_closed for client in clients)
    still_pending = [task for task in asyncio.all_tasks(loops[0]) if not task.done()]
    assert still_pending == []


def test_a_failing_closer_neither_skips_the_rest_nor_the_engine_dispose(
    container: Container, qapp, monkeypatch
):
    calls: list[str] = []

    async def failing() -> None:
        calls.append("failing")
        raise RuntimeError("boom")

    async def healthy() -> None:
        calls.append("healthy")

    disposed: list[bool] = []
    monkeypatch.setattr(container.engine, "dispose", lambda *a, **kw: disposed.append(True))
    wired = dataclasses.replace(container, closers=(failing, healthy))

    exit_code = Application(wired, qapp).run(on_started=lambda: QTimer.singleShot(20, qapp.quit))

    assert exit_code == 0
    assert calls == ["failing", "healthy"]  # in order, and the failure didn't stop the next one
    assert disposed == [True]


def test_main_closes_every_http_client_it_opens(tmp_path: Path, qapp, monkeypatch):
    clients = _record_http_clients(monkeypatch)
    monkeypatch.setattr(main_module, "load_config", lambda: _config(tmp_path))
    monkeypatch.setattr(main_module, "QGuiApplication", lambda argv: qapp)
    real_run = Application.run
    monkeypatch.setattr(
        Application,
        "run",
        lambda self, **kw: real_run(self, on_started=lambda: QTimer.singleShot(20, qapp.quit)),
    )

    assert main_module.main() == 0

    # download engine's client + the one Twitch and Kick share
    assert len(clients) >= 2
    assert [client.is_closed for client in clients] == [True] * len(clients)


async def test_task_runner_cancel_all_cancels_pending_tasks_and_waits_for_them():
    runner = TaskRunner(asyncio.get_running_loop().create_task)
    started = asyncio.Event()
    cancelled: list[bool] = []

    async def forever() -> None:
        started.set()
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    runner.run(forever())
    await started.wait()

    await runner.cancel_all()

    assert cancelled == [True]
    assert [task for task in asyncio.all_tasks() if task is not asyncio.current_task()] == []


def test_python_dash_m_twick_hub_is_importable_without_starting_the_app():
    import importlib

    module = importlib.import_module("twick_hub.__main__")

    assert module.main is main_module.main


def test_the_startup_log_line_no_longer_says_skeleton(container: Container, qapp, caplog):
    caplog.set_level("INFO", logger="twick_hub.bootstrap.application")

    Application(container, qapp).run(on_started=lambda: QTimer.singleShot(20, qapp.quit))

    messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == "twick_hub.bootstrap.application"
    ]
    assert "Twick Hub started." in messages
    assert not any("skeleton" in message for message in messages)


def test_a_qml_load_failure_still_closes_the_resources_and_the_loop(
    container: Container, qapp, monkeypatch
):
    """The early ``return 1`` used to skip shutdown entirely: the loop was
    never closed and the container's closers and ``engine.dispose()`` never
    ran."""
    import twick_hub.bootstrap.application as application_module

    monkeypatch.setattr(
        application_module, "_QML_MAIN", application_module._QML_MAIN.parent / "DoesNotExist.qml"
    )
    calls: list[str] = []

    async def closer() -> None:
        calls.append("closer")

    disposed: list[bool] = []
    monkeypatch.setattr(container.engine, "dispose", lambda *a, **kw: disposed.append(True))
    loops: list[asyncio.AbstractEventLoop] = []
    real_set_event_loop = asyncio.set_event_loop
    monkeypatch.setattr(
        asyncio,
        "set_event_loop",
        lambda loop: (loops.append(loop), real_set_event_loop(loop))[1],
    )

    exit_code = Application(dataclasses.replace(container, closers=(closer,)), qapp).run()

    assert exit_code == 1
    assert calls == ["closer"]
    assert disposed == [True]
    assert loops and loops[0].is_closed()
