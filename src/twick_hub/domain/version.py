"""A minimal, pure semantic-version comparator — just enough to answer
"is this update actually newer" (Master Plan §51: "Verificar: ... versiones"),
which matters for security as much as correctness: an attacker who replays
an old, validly-signed manifest (RISK: downgrade/rollback attack) must not
be able to talk the app into "updating" to an older, vulnerable release.

Not a full PEP 440 / semver implementation — no build metadata, no
operator ranges. ``MAJOR.MINOR.PATCH`` with an optional ``-prerelease``
suffix (``2.1.0-rc1``), which is what ``pyproject.toml``'s own
``version`` field already uses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$")


class InvalidVersionError(ValueError):
    pass


@dataclass(frozen=True, order=False, slots=True)
class Version:
    major: int
    minor: int
    patch: int
    prerelease: str | None = None  # e.g. "rc1"; None means a final release

    @classmethod
    def parse(cls, text: str) -> Version:
        match = _PATTERN.match(text.strip())
        if match is None:
            raise InvalidVersionError(
                f"not a valid MAJOR.MINOR.PATCH[-prerelease] version: {text!r}"
            )
        major, minor, patch, prerelease = match.groups()
        return cls(int(major), int(minor), int(patch), prerelease)

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        return f"{base}-{self.prerelease}" if self.prerelease else base

    def _sort_key(self) -> tuple:
        # A final release outranks any prerelease of the same
        # MAJOR.MINOR.PATCH (semver's own rule) — so a prerelease sorts
        # as "less than" None, not compared as a string against it.
        return (self.major, self.minor, self.patch, self.prerelease is None, self.prerelease or "")

    def __lt__(self, other: Version) -> bool:
        if self.prerelease is None and other.prerelease is None:
            return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)
        if (self.major, self.minor, self.patch) != (other.major, other.minor, other.patch):
            return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)
        if self.prerelease is None:
            return False  # a final release is never less than a prerelease of the same X.Y.Z
        if other.prerelease is None:
            return True  # a prerelease is always less than a final release of the same X.Y.Z
        return self.prerelease < other.prerelease

    def __le__(self, other: Version) -> bool:
        return self == other or self < other

    def __gt__(self, other: Version) -> bool:
        return other < self

    def __ge__(self, other: Version) -> bool:
        return self == other or other < self
