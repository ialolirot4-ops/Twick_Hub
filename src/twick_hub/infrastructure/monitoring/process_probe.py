"""Reads this process's own CPU time and resident memory — the real
``application.live_monitor.metrics.ResourceProbe``.

``psutil`` is the one dependency FASE 10 adds, and only here: measuring a
process's resident set size portably needs a different OS call on
Windows (the confirmed target, docs/architecture-decisions.md AD-10),
Linux, and macOS, and hand-rolling the Windows one with ``ctypes`` would
be code nobody on this project can test from a non-Windows sandbox.
"""

from __future__ import annotations

import psutil

from twick_hub.application.live_monitor.metrics import ResourceSample


class PsutilResourceProbe:
    def __init__(self) -> None:
        self._process = psutil.Process()

    def sample(self) -> ResourceSample:
        cpu = self._process.cpu_times()
        return ResourceSample(
            cpu_seconds=cpu.user + cpu.system,
            rss_bytes=self._process.memory_info().rss,
        )
