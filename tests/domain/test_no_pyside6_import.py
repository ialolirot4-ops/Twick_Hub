"""Regression guard for the FASE 3 requirement stated verbatim in the
Master Plan: "Domain no importa PySide6."

Checks for actual ``import``/``from ... import`` statements, not just the
string "PySide6" anywhere in a file — several domain files mention it in
their own docstrings precisely to explain that it's absent, which a
naive substring search would misreport as a violation.
"""

from __future__ import annotations

import re
from pathlib import Path

_DOMAIN_DIR = Path(__file__).resolve().parents[2] / "src" / "twick_hub" / "domain"
_FORBIDDEN_IMPORT = re.compile(r"^\s*(import|from)\s+(PySide6|PyQt6|qasync)\b", re.MULTILINE)


def test_no_domain_file_imports_pyside6():
    offenders = []
    for path in _DOMAIN_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if _FORBIDDEN_IMPORT.search(text):
            offenders.append(path.relative_to(_DOMAIN_DIR.parent))

    assert offenders == [], f"Domain files importing a Qt/asyncio-loop framework: {offenders}"
