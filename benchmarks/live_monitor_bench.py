"""Reproducible, SYNTHETIC measurements for the FASE 10 live monitor.

    python benchmarks/live_monitor_bench.py

What this measures (no real network — Twitch/Kick aren't reachable from
this project's sandbox, so anything about real latency, real rate limits or
real payload sizes is PENDING a run against real accounts):

1. **Per-poll overhead**: the monitor's own CPU and memory cost for one
   poll of N channels, using the real ``KickBatchLiveStatusProvider`` +
   ``PollingLiveMonitor`` + ``LiveStateTracker`` over an in-process
   ``httpx.MockTransport`` (JSON encode/decode and httpx included, sockets
   excluded).
2. **Requests per hour** under the adaptive policy, by stepping
   ``AdaptiveInterval`` through one simulated hour — compared with the
   naive alternative of polling every channel individually.

CPU is process-wide (psutil), so it includes the benchmark harness itself;
treat the numbers as an upper bound on the monitor's own cost.
"""

from __future__ import annotations

import asyncio
import json
import time

import httpx

from twick_hub.application.live_monitor.polling_monitor import PollingLiveMonitor
from twick_hub.application.live_monitor.polling_policy import AdaptiveInterval, PollingConfig
from twick_hub.application.live_monitor.tracker import LiveStateTracker
from twick_hub.domain.enums import Platform
from twick_hub.domain.events import EventBus
from twick_hub.domain.value_objects import PlatformRef
from twick_hub.infrastructure.kick.client import KickAPIClient
from twick_hub.infrastructure.kick.livestream_batch import KickBatchLiveStatusProvider
from twick_hub.infrastructure.monitoring.process_probe import PsutilResourceProbe


def _kick_handler(live_fraction: float):
    def handler(request: httpx.Request) -> httpx.Response:
        ids = request.url.params.get_list("broadcaster_user_id")
        live = ids[: int(len(ids) * live_fraction)]
        data = [
            {
                "broadcaster_user_id": int(i),
                "slug": f"c{i}",
                "stream_title": "benchmark stream title",
                "viewer_count": 100,
                "started_at": "2026-09-01T10:00:00Z",
                "category": {"id": 1, "name": "Just Chatting"},
                "thumbnail": "https://example.invalid/t.webp",
            }
            for i in live
        ]
        return httpx.Response(200, content=json.dumps({"data": data}))

    return handler


async def per_poll_overhead(channels: int, polls: int) -> dict:
    client = httpx.AsyncClient(transport=httpx.MockTransport(_kick_handler(0.2)))
    provider = KickBatchLiveStatusProvider(KickAPIClient(client, lambda: "token"))
    monitor = PollingLiveMonitor(provider, LiveStateTracker(EventBus()))
    for i in range(1, channels + 1):
        await monitor.subscribe(PlatformRef(platform=Platform.KICK, external_id=str(i)))
    probe = PsutilResourceProbe()

    await monitor.poll_once()  # warm-up (first sighting publishes events)
    before = probe.sample()
    started = time.perf_counter()
    for _ in range(polls):
        await monitor.poll_once()
    wall = time.perf_counter() - started
    after = probe.sample()

    stats = monitor.stats()
    return {
        "channels": channels,
        "polls": polls,
        "http_requests_per_poll": stats.requests / stats.polls,
        "ms_per_poll": round(wall / polls * 1000, 2),
        "cpu_ms_per_poll": round((after.cpu_seconds - before.cpu_seconds) / polls * 1000, 2),
        "rss_mb": round((after.rss_bytes or 0) / 1e6, 1),
        "rss_delta_kb": round(((after.rss_bytes or 0) - (before.rss_bytes or 0)) / 1e3, 1),
    }


def simulated_requests_per_hour(
    config: PollingConfig, *, change_every_seconds: float | None
) -> int:
    policy = AdaptiveInterval(config, rng=lambda: 0.5)  # mid-range jitter, deterministic
    now, requests, next_change = 0.0, 0, change_every_seconds
    while True:
        now += policy.next_delay()
        if now > 3600:
            return requests
        requests += 1
        changed = next_change is not None and now >= next_change
        if changed and change_every_seconds is not None:
            next_change = now + change_every_seconds
        policy.record_success(changed=changed)


def main() -> None:
    print("== per-poll overhead (synthetic: in-process transport, no sockets) ==")
    for channels in (10, 50, 500):
        print(json.dumps(asyncio.run(per_poll_overhead(channels, polls=200))))

    default = PollingConfig()
    reconcile = PollingConfig(base_interval=900, max_quiet_interval=900, max_backoff_interval=1800)
    print("\n== requests per simulated hour ==")
    rows = {
        "fast poller, nothing ever changes": simulated_requests_per_hour(
            default, change_every_seconds=None
        ),
        "fast poller, a change every 10 min": simulated_requests_per_hour(
            default, change_every_seconds=600
        ),
        "reconcile poller (push-covered channels)": simulated_requests_per_hour(
            reconcile, change_every_seconds=None
        ),
    }
    for name, count in rows.items():
        print(f"{name:45s} {count:4d} requests/h")

    print("\n== the same 20 Twitch favorites, requests per hour ==")
    fast = rows["fast poller, nothing ever changes"]
    print(f"naive: one poll per channel every 60 s      {20 * 60:5d}")
    print(f"batched polling only (1 request per poll)   {fast:5d}")
    print(
        "EventSub (5) + batched fast poll (15) + reconcile (5): "
        f"{fast + rows['reconcile poller (push-covered channels)']:d} poll requests "
        "(+10 one-time EventSub subscriptions)"
    )


if __name__ == "__main__":
    main()
