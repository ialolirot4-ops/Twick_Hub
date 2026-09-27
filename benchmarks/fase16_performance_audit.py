"""FASE 16 — Performance Audit.

    python benchmarks/fase16_performance_audit.py

Measures the Master Plan §53 checklist against the REAL pipeline wherever
one exists in this codebase today, and says explicitly where it doesn't
(this project has no wired Container beyond `favorites` — RISK-ARCH-04 —
and no thumbnail-cache code at all — RISK-UI-02). No numbers are invented
for anything not actually implemented yet.

Real, not mocked, in this run:
  - startup: the actual `build_container()` + `QGuiApplication` +
    `QQmlApplicationEngine.load(Main.qml)` path from bootstrap/.
  - downloads: a real local HTTP server (stdlib `http.server`) serving a
    real HLS media playlist + 6 real `.ts` segments (encoded by ffmpeg,
    `testsrc` pattern, ~62 KB each) to the REAL `HlsPlaylistReader` +
    `HttpxSegmentFetcher` + `SegmentManager` + `FFmpegProcessor`
    (`/usr/bin/ffmpeg`, real subprocess) — the same
    `DownloadExecutor._run` a production job runs, only `resolve_playback`
    is faked (points at the local server instead of Twitch/Kick, since
    this sandbox has no network to either).
  - live monitor CPU: reuses FASE 10's own httpx.MockTransport approach
    (see live_monitor_bench.py) for Kick polling, plus a real local
    `websockets` server standing in for Twitch's EventSub endpoint so the
    REAL `TwitchEventSubProvider` reconnect/keepalive loop runs against a
    real socket (still not the real twitch.tv — no network to it here).

NOT measured (explicitly, not silently skipped):
  - thumbnail cache: no code exists yet (RISK-UI-02) — nothing to run.
  - UI responsiveness under real user interaction: Main.qml has no real
    pages wired to live data yet (RISK-ARCH-01) — what IS measured is
    whether the Qt event loop keeps servicing a QTimer at its configured
    interval while a real download's asyncio/ffmpeg work runs alongside
    it (qasync bridge), which is the one UI-responsiveness question this
    codebase's current state can actually answer.
  - "visible vs minimized": no code branches on window visibility yet
    (grep confirms only a `minimize_to_tray` settings *field* exists) —
    so visible/minimized would be the same measurement twice. Skipped
    rather than duplicated.
"""

from __future__ import annotations

import asyncio
import contextlib
import http.server
import json
import os
import statistics
import sys
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import httpx  # noqa: E402
import psutil  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

SEGMENTS_DIR = Path(os.environ.get("FASE16_SEGMENTS_DIR", "/home/claude/work/bench_segments"))
RESULTS_PATH = REPO_ROOT / "benchmarks" / "fase16_results.json"

PROCESS = psutil.Process()


def _cpu_seconds() -> float:
    t = PROCESS.cpu_times()
    return t.user + t.system


def _rss_bytes() -> int:
    return PROCESS.memory_info().rss


# --------------------------------------------------------------------------
# 1. Startup
# --------------------------------------------------------------------------


def measure_startup(runs: int = 5) -> dict:
    """Real `build_container()` + `QGuiApplication` + Main.qml load, timed
    end to end, `runs` times in the same process (first run pays import
    cost; reported both ways)."""
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine

    from twick_hub.bootstrap.dependencies import build_container
    from twick_hub.config.settings import AppConfig
    from twick_hub.presentation import qml_bridge  # noqa: F401  (registers QML singletons)

    _qt_app = QGuiApplication.instance() or QGuiApplication([])
    qml_main = REPO_ROOT / "src" / "twick_hub" / "presentation" / "qml" / "Main.qml"

    durations = []
    for i in range(runs):
        db_path = f"/tmp/fase16_startup_{i}.sqlite"
        Path(db_path).unlink(missing_ok=True)
        config = AppConfig(app_name="Twick Hub (bench)", database_url=f"sqlite:///{db_path}")

        t0 = time.perf_counter()
        container = build_container(config)
        engine = QQmlApplicationEngine()
        engine.load(QUrl.fromLocalFile(str(qml_main)))
        loaded = bool(engine.rootObjects())
        t1 = time.perf_counter()

        engine.deleteLater()
        container.engine.dispose()
        Path(db_path).unlink(missing_ok=True)
        durations.append(t1 - t0)
        if not loaded:
            raise RuntimeError("Main.qml failed to load — startup benchmark invalid")

    median_subsequent = statistics.median(durations[1:]) if len(durations) > 1 else None
    return {
        "first_run_seconds": durations[0],
        "subsequent_runs_seconds": durations[1:],
        "median_subsequent_seconds": median_subsequent,
    }


# --------------------------------------------------------------------------
# 2. Idle CPU / RAM
# --------------------------------------------------------------------------


async def measure_idle(seconds: float = 5.0) -> dict:
    """No jobs, no polling, nothing scheduled — just the asyncio loop
    itself alive, matching the "sin trabajo" row of the Master Plan's
    measurement matrix."""
    cpu0, rss_samples = _cpu_seconds(), []
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < seconds:
        rss_samples.append(_rss_bytes())
        await asyncio.sleep(0.5)
    cpu1 = _cpu_seconds()
    return {
        "duration_seconds": seconds,
        "cpu_seconds_consumed": cpu1 - cpu0,
        "cpu_percent_of_wallclock": (cpu1 - cpu0) / seconds * 100,
        "rss_bytes_min": min(rss_samples),
        "rss_bytes_max": max(rss_samples),
    }


# --------------------------------------------------------------------------
# 3. Downloads (1 and 4 concurrent) — real HTTP + real ffmpeg
# --------------------------------------------------------------------------


class _Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:  # silence stdout spam
        pass


def _start_local_server(directory: Path) -> tuple[http.server.ThreadingHTTPServer, str]:
    handler = lambda *a, **kw: _Handler(*a, directory=str(directory), **kw)  # noqa: E731
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    return server, f"http://127.0.0.1:{port}"


def _write_playlist(directory: Path, segment_names: list[str]) -> None:
    lines = ["#EXTM3U", "#EXT-X-VERSION:3", "#EXT-X-TARGETDURATION:2", "#EXT-X-MEDIA-SEQUENCE:0"]
    for name in segment_names:
        lines += ["#EXTINF:2.0,", name]
    lines.append("#EXT-X-ENDLIST")
    (directory / "media.m3u8").write_text("\n".join(lines) + "\n")


async def _run_one_download(
    base_url: str, work_dir: Path, download_id: str
) -> tuple[float, float, int]:
    """Drives the REAL DownloadExecutor pipeline for one job. Returns
    (wall_seconds, cpu_seconds, output_bytes)."""
    from twick_hub.application.platform_registry import PlatformAdapters, PlatformRegistry
    from twick_hub.domain.downloads import Download
    from twick_hub.domain.enums import MediaKind, Platform
    from twick_hub.domain.value_objects import Media, PlatformRef, PlaybackSource
    from twick_hub.infrastructure.downloads.download_executor import DownloadExecutor
    from twick_hub.infrastructure.downloads.ffmpeg_processor import (
        AsyncioProcessRunner,
        FFmpegProcessor,
    )
    from twick_hub.infrastructure.downloads.hls import HlsPlaylistReader
    from twick_hub.infrastructure.downloads.media_processor import MediaProcessor
    from twick_hub.infrastructure.downloads.progress_tracker import ProgressTracker
    from twick_hub.infrastructure.downloads.retry_policy import RetryPolicy
    from twick_hub.infrastructure.downloads.segment_manager import (
        HttpxSegmentFetcher,
        SegmentManager,
    )

    sys.path.insert(0, str(REPO_ROOT))
    from tests.application.fakes import InMemoryDownloadRepository  # noqa: E402

    class _LocalPlaybackResolver:
        async def resolve(self, media, quality) -> PlaybackSource:
            return PlaybackSource(url=f"{base_url}/media.m3u8", quality_label=quality)

        async def available_qualities(self, media):
            return ["source"]

    media = Media(
        kind=MediaKind.STREAM,
        ref=PlatformRef(platform=Platform.TWITCH, external_id=f"bench-{download_id}"),
        title="FASE16 benchmark stream",
    )
    downloads_repo = InMemoryDownloadRepository()
    output_path = work_dir / f"{download_id}.ts"
    download = Download(
        id=download_id,
        media=media,
        destination_path=str(output_path),
        quality_label="source",
    )
    await downloads_repo.save(download)

    registry = PlatformRegistry(
        {Platform.TWITCH: PlatformAdapters(playback_resolver=_LocalPlaybackResolver())}
    )

    async with httpx.AsyncClient() as http_client:
        hls_reader = HlsPlaylistReader(http_client)
        segment_manager = SegmentManager(
            fetcher=HttpxSegmentFetcher(http_client),
            retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=0.1),
            progress=ProgressTracker(),
        )
        media_processor = MediaProcessor(ffmpeg=FFmpegProcessor(runner=AsyncioProcessRunner()))
        executor = DownloadExecutor(
            registry=registry,
            downloads=downloads_repo,
            hls_reader=hls_reader,
            segment_manager=segment_manager,
            media_processor=media_processor,
            work_dir=work_dir,
            poll_interval_seconds=0.05,
        )

        cpu0 = _cpu_seconds()
        t0 = time.perf_counter()
        await executor.run(download_id, is_cancelled=lambda: False, is_paused=lambda: False)
        t1 = time.perf_counter()
        cpu1 = _cpu_seconds()

    final = await downloads_repo.get(download_id)
    if final is None or final.status.name != "COMPLETED":
        raise RuntimeError(f"download {download_id} did not complete: {final}")

    return t1 - t0, cpu1 - cpu0, output_path.stat().st_size


async def measure_downloads(base_url: str, concurrency: int) -> dict:
    work_dir = Path(f"/tmp/fase16_downloads_{concurrency}")
    work_dir.mkdir(parents=True, exist_ok=True)

    rss0 = _rss_bytes()
    t0 = time.perf_counter()
    results = await asyncio.gather(
        *(_run_one_download(base_url, work_dir, f"job{i}") for i in range(concurrency))
    )
    t1 = time.perf_counter()
    rss_peak = max(_rss_bytes(), rss0)

    return {
        "concurrency": concurrency,
        "wall_seconds_total": t1 - t0,
        "per_job_wall_seconds": [r[0] for r in results],
        "per_job_cpu_seconds": [r[1] for r in results],
        "output_bytes_each": [r[2] for r in results],
        "rss_delta_bytes": rss_peak - rss0,
    }


# --------------------------------------------------------------------------
# 4. Live monitor CPU + network requests (Kick polling, real math from
#    FASE 10's own AdaptiveInterval; Twitch EventSub against a real local
#    websocket server standing in for wss://eventsub.wss.twitch.tv)
# --------------------------------------------------------------------------


async def measure_kick_polling(channel_count: int, simulated_hours: float = 1.0) -> dict:
    """Delegates to FASE 10's own live_monitor_bench.py rather than
    re-deriving the same math — reuses its real
    KickBatchLiveStatusProvider + httpx.MockTransport per-poll overhead
    measurement and its AdaptiveInterval requests/hour simulation."""
    sys.path.insert(0, str(REPO_ROOT / "benchmarks"))
    import live_monitor_bench as lmb  # noqa: E402

    from twick_hub.application.live_monitor.polling_policy import PollingConfig

    overhead = await lmb.per_poll_overhead(channels=channel_count, polls=100)
    default_config = PollingConfig()
    requests_per_hour_idle = lmb.simulated_requests_per_hour(
        default_config, change_every_seconds=None
    )
    naive_requests_per_hour = channel_count * (3600 / default_config.base_interval)
    return {
        "channel_count": channel_count,
        "per_poll_overhead": overhead,
        "adaptive_requests_per_hour_idle_channel": requests_per_hour_idle,
        "naive_per_channel_polling_requests_per_hour_equivalent": naive_requests_per_hour,
    }


async def measure_twitch_eventsub_local() -> dict:
    """Runs the REAL TwitchEventSubProvider connection loop against a real
    local `websockets` server that speaks just enough of the protocol
    (session_welcome + one keepalive) to exercise the reconnect-free happy
    path. Measures CPU/RSS while it idles on that real connection — NOT a
    substitute for a real twitch.tv run (no network to it here)."""
    import uuid

    import websockets

    from twick_hub.domain.events import EventBus
    from twick_hub.infrastructure.twitch.eventsub.connection import connect_real
    from twick_hub.infrastructure.twitch.eventsub.provider import TwitchEventSubProvider

    async def _fake_twitch_server(ws):
        await ws.send(
            json.dumps(
                {
                    "metadata": {
                        "message_id": uuid.uuid4().hex,
                        "message_type": "session_welcome",
                    },
                    "payload": {
                        "session": {"id": "bench-session", "keepalive_timeout_seconds": 10}
                    },
                }
            )
        )
        try:
            while True:
                await asyncio.sleep(3.0)
                await ws.send(
                    json.dumps(
                        {
                            "metadata": {
                                "message_id": uuid.uuid4().hex,
                                "message_type": "session_keepalive",
                            },
                            "payload": {},
                        }
                    )
                )
        except (asyncio.CancelledError, websockets.exceptions.ConnectionClosed):
            pass

    class _UnusedLiveStreamProvider:
        """No subscription is created in this benchmark (connection-only
        happy path), so this is never actually called — a real object
        instead of None just satisfies the protocol/type-checker."""

        async def get_live_stream(self, channel_ref):
            raise NotImplementedError

    async with websockets.serve(_fake_twitch_server, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        local_url = f"ws://127.0.0.1:{port}"

        provider = TwitchEventSubProvider(
            http_client=httpx.AsyncClient(),
            live_stream_provider=_UnusedLiveStreamProvider(),
            user_token_getter=lambda: "bench-token",
            event_bus=EventBus(),
            connector=lambda url: connect_real(local_url),
        )

        cpu0 = _cpu_seconds()
        rss0 = _rss_bytes()
        t0 = time.perf_counter()

        run_task = asyncio.create_task(provider.run_forever())
        await asyncio.sleep(8.0)  # long enough to see >=1 keepalive round-trip

        t1 = time.perf_counter()
        cpu1 = _cpu_seconds()
        rss1 = _rss_bytes()

        await provider.stop()
        run_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await run_task
        await provider._http.aclose()

    return {
        "wall_seconds": t1 - t0,
        "cpu_seconds": cpu1 - cpu0,
        "cpu_percent_of_wallclock": (cpu1 - cpu0) / (t1 - t0) * 100,
        "rss_delta_bytes": rss1 - rss0,
        "note": "local ws:// server, not real wss://eventsub.wss.twitch.tv (no network to it here)",
    }


# --------------------------------------------------------------------------
# 5. UI responsiveness during a download (Qt event loop under qasync)
# --------------------------------------------------------------------------


def measure_ui_responsiveness_during_download(base_url: str) -> dict:
    import qasync
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QGuiApplication

    qt_app = QGuiApplication.instance() or QGuiApplication([])
    loop = qasync.QEventLoop(qt_app)
    asyncio.set_event_loop(loop)

    tick_times: list[float] = []
    timer = QTimer()
    timer.setInterval(50)  # ms
    timer.timeout.connect(lambda: tick_times.append(time.perf_counter()))

    async def _main():
        timer.start()
        work_dir = Path("/tmp/fase16_ui_responsiveness")
        work_dir.mkdir(parents=True, exist_ok=True)
        # One download finishes in ~0.1s — too short to see timer jitter.
        # Run several back-to-back so the event loop stays busy with real
        # asyncio/httpx/ffmpeg work for long enough to sample gaps.
        for i in range(20):
            await _run_one_download(base_url, work_dir, f"ui-check-{i}")
        timer.stop()

    with loop:
        loop.run_until_complete(_main())

    if len(tick_times) < 3:
        return {"ticks_recorded": len(tick_times), "note": "too few ticks to measure jitter"}

    gaps_ms = [(b - a) * 1000 for a, b in zip(tick_times, tick_times[1:], strict=False)]
    return {
        "expected_interval_ms": 50,
        "ticks_recorded": len(tick_times),
        "gap_ms_median": statistics.median(gaps_ms),
        "gap_ms_max": max(gaps_ms),
        "gap_ms_p95": sorted(gaps_ms)[int(len(gaps_ms) * 0.95)],
    }


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def main() -> None:
    results: dict = {}

    print("== 1. Startup ==")
    results["startup"] = measure_startup()
    print(json.dumps(results["startup"], indent=2))

    print("\n== 2. Idle CPU/RAM (5s, sin trabajo) ==")
    results["idle"] = asyncio.run(measure_idle(5.0))
    print(json.dumps(results["idle"], indent=2))

    print("\n== 3. Downloads (real HTTP + real ffmpeg) ==")
    server, base_url = _start_local_server(SEGMENTS_DIR)
    segment_names = sorted(p.name for p in SEGMENTS_DIR.glob("*.ts"))
    _write_playlist(SEGMENTS_DIR, segment_names)
    try:
        results["download_1"] = asyncio.run(measure_downloads(base_url, concurrency=1))
        print(json.dumps(results["download_1"], indent=2))
        results["download_4"] = asyncio.run(measure_downloads(base_url, concurrency=4))
        print(json.dumps(results["download_4"], indent=2))

        print("\n== 5. UI responsiveness during 1 download ==")
        results["ui_responsiveness"] = measure_ui_responsiveness_during_download(base_url)
        print(json.dumps(results["ui_responsiveness"], indent=2))
    finally:
        server.shutdown()

    print("\n== 4a. Kick adaptive polling (5 channels, 1h simulated) ==")
    results["kick_polling"] = asyncio.run(measure_kick_polling(channel_count=5))
    print(json.dumps(results["kick_polling"], indent=2))

    print("\n== 4b. Twitch EventSub connection (local ws://, not real Twitch) ==")
    results["twitch_eventsub_local"] = asyncio.run(measure_twitch_eventsub_local())
    print(json.dumps(results["twitch_eventsub_local"], indent=2))

    results["not_measured"] = {
        "thumbnail_cache": "no thumbnail-cache code exists yet (RISK-UI-02) — nothing to run",
        "visible_vs_minimized": (
            "no code branches on window visibility yet (only a minimize_to_tray "
            "settings field exists) — would duplicate the same measurement"
        ),
        "twitch_eventsub_real_network": "no network to twitch.tv from this sandbox",
        "kick_live_requests_real_network": "no network to kick.com from this sandbox",
    }

    RESULTS_PATH.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nWrote {RESULTS_PATH}")


if __name__ == "__main__":
    main()
