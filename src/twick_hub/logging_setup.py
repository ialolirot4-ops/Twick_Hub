"""Logging configuration.

Called exactly once, from ``bootstrap/dependencies.py``. No other module
configures logging — every module gets its logger via
``logging.getLogger(__name__)`` and relies on this call having already run.
"""

from __future__ import annotations

import logging
import sys

from twick_hub.config.settings import AppConfig


def configure_logging(config: AppConfig) -> None:
    root = logging.getLogger()

    if root.handlers:
        # Idempotent: build_container() may run more than once within a
        # single process (every test that uses the `container` fixture
        # does exactly that), and re-adding handlers would duplicate
        # every log line.
        root.setLevel(config.log_level)
        return

    root.setLevel(config.log_level)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s"))
    root.addHandler(handler)
