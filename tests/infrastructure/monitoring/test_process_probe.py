from __future__ import annotations

from twick_hub.application.live_monitor.metrics import ResourceProbe
from twick_hub.infrastructure.monitoring.process_probe import PsutilResourceProbe


def test_probe_reads_real_cpu_and_memory_of_this_process():
    probe = PsutilResourceProbe()

    first = probe.sample()
    sum(i * i for i in range(300_000))  # burn a little CPU
    second = probe.sample()

    assert isinstance(probe, ResourceProbe)
    assert first.rss_bytes is not None and first.rss_bytes > 1_000_000  # a Python process is > 1 MB
    assert second.cpu_seconds >= first.cpu_seconds
