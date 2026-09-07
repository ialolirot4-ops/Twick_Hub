"""Regression guard for the FASE 1 requirement stated verbatim in the
Master Plan: "evitar efectos secundarios por imports."

Runs in a fresh subprocess (not in-process) because every other test in
this suite calls ``build_container()``, which configures the root
logger — checking "no handlers yet" in the same process as those tests
would be order-dependent and unreliable. A subprocess gives a real,
untouched interpreter to import into.
"""

from __future__ import annotations

import subprocess
import sys

_PROBE = """
import logging
import twitchlink_next.main  # noqa: F401
import twitchlink_next.bootstrap.dependencies  # noqa: F401

# If either import above had constructed a QGuiApplication, opened a
# database connection, or configured logging as a side effect (the
# TwitchLink 3.5.5 `Core/App.py` pattern this project explicitly
# removes — docs/architecture-decisions.md AD-03), one of these would
# already be non-empty/non-None by this point, before anything was
# ever called.
assert logging.getLogger().handlers == [], "import configured logging as a side effect"

from PySide6.QtGui import QGuiApplication
assert QGuiApplication.instance() is None, "import constructed a QGuiApplication as a side effect"

print("OK")
"""


def test_importing_bootstrap_modules_has_no_side_effects():
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True,
        text=True,
        env={"QT_QPA_PLATFORM": "offscreen", "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "OK"
