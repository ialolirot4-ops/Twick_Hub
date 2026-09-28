"""FASE 22.1: no QML action may claim something the app did not do.

Until now four pages answered a button with a toast that leaked a phase
number ("... isn't wired up yet — that's FASE 12") and two more announced
success for work that never happened ("Everything is up to date" after a
timer, "Settings reset to defaults" with nothing reset). A static scan is
the cheapest guard against that coming back while the pages are still
being wired up one by one.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_QML = Path(__file__).resolve().parents[1] / "src/twick_hub/presentation/qml"

# Toast calls that talk about the project's own phases or wiring status.
_LEAKS_INTERNALS = re.compile(r"ToastController\.\w+\(.*(wired up|FASE\s*\d)", re.IGNORECASE)

# Success messages that were shown without doing the thing.
_FALSE_SUCCESS = (
    "Everything is up to date",
    "Settings reset to defaults",
)


def _qml_files() -> list[Path]:
    files = sorted(_QML.rglob("*.qml"))
    assert files, f"no QML files found under {_QML}"
    return files


@pytest.mark.parametrize("path", _qml_files(), ids=lambda p: p.relative_to(_QML).as_posix())
def test_no_qml_file_makes_a_claim_the_app_did_not_earn(path: Path):
    offending: list[str] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if _LEAKS_INTERNALS.search(line):
            offending.append(f"{path.name}:{number}: leaks phase/wiring status: {line.strip()}")
        for phrase in _FALSE_SUCCESS:
            if phrase in line:
                offending.append(f"{path.name}:{number}: unearned success message: {phrase!r}")
    assert offending == []
