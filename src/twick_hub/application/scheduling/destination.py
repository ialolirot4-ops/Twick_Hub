"""Where a recording's file goes: directory + filename template, made safe.

Everything that reaches a path here is untrusted text — a stream title can
contain ``/``, ``:``, ``..``, a Windows reserved name, or 300 characters.
Values are sanitized *before* they are substituted, so any ``/`` left in
the rendered pattern was written by the user in their own template and
means "subfolder"; nothing a streamer types can add a path component.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Collection, Mapping
from pathlib import Path

from twick_hub.domain.value_objects import FilenameTemplate

DEFAULT_TEMPLATE = "{channel}/{title} ({date})"
DEFAULT_EXTENSION = "mp4"

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}  # fmt: skip
_MAX_COMPONENT = 100


def sanitize_component(text: str) -> str:
    cleaned = _ILLEGAL.sub("_", text).strip(" .")
    cleaned = cleaned[:_MAX_COMPONENT].rstrip(" .")
    if not cleaned or cleaned in (".", ".."):
        return "_"
    if cleaned.split(".")[0].lower() in _RESERVED:
        return f"_{cleaned}"
    return cleaned


class DestinationPlanner:
    def __init__(
        self,
        default_directory: Path,
        template: str = DEFAULT_TEMPLATE,
        exists: Callable[[Path], bool] = Path.exists,
    ) -> None:
        self._default_directory = default_directory
        self._template = FilenameTemplate(template)
        self._exists = exists

    def plan(
        self,
        values: Mapping[str, str],
        *,
        directory: str | None = None,
        extension: str | None = None,
        reserved: Collection[str] = (),
    ) -> str:
        """A path that exists neither on disk nor in ``reserved`` (the
        destinations of downloads still in flight, whose files may not have
        been created yet)."""
        safe_values = {key: sanitize_component(value) for key, value in values.items()}
        rendered = self._template.render(safe_values).replace("\\", "/")
        parts = [sanitize_component(part) for part in rendered.split("/") if part.strip()]
        if not parts:
            parts = ["recording"]
        ext = (
            re.sub(r"[^a-z0-9]", "", (extension or DEFAULT_EXTENSION).lower()) or DEFAULT_EXTENSION
        )

        base = Path(directory) if directory else self._default_directory
        folder = base.joinpath(*parts[:-1])
        stem = parts[-1]
        taken = set(reserved)
        candidate = folder / f"{stem}.{ext}"
        counter = 2
        while self._exists(candidate) or str(candidate) in taken:
            candidate = folder / f"{stem} ({counter}).{ext}"
            counter += 1
        return str(candidate)
