"""Turns a stored quality *preference* ("best", "720p", "audio-only", ...)
into one of the labels a playback resolver actually offers.

Preferences are what a person saves on a favorite or a scheduled download
(ported from 3.5.5's ``ScheduledDownloadPreset.AVAILABLE_QUALITY``: best,
1080p/720p/480p/360p/160p, worst, audio-only); labels are what a stream
offers *right now* ("1080p60", "720p60", "audio_only"). They can disagree —
a channel streaming at 720p has no "1080p" — and a recording that silently
does nothing because of that would be worse than one at the wrong quality.
So an unavailable preference falls back to the best quality and says so
(``QualityChoice.fell_back``), matching 3.5.5's default behaviour when
"preferred resolution only" is off.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

_LABEL = re.compile(r"^(\d+)p(\d+)?$", re.IGNORECASE)
_BEST = {"best", "source"}
_AUDIO = {"audio-only", "audio_only", "audio only", "audio"}


class NoQualitiesError(Exception):
    """The platform offered no playable quality at all."""


@dataclass(frozen=True, slots=True)
class QualityChoice:
    label: str
    fell_back: bool = False


def _is_audio(label: str) -> bool:
    return "audio" in label.lower()


def _height_and_fps(label: str) -> tuple[int, int] | None:
    match = _LABEL.match(label.strip())
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2) or 0)


def select_quality(preference: str, available: Sequence[str]) -> QualityChoice:
    """``available`` is expected best-first, as ``PlaybackResolver`` returns it."""
    if not available:
        raise NoQualitiesError("no playable qualities")
    video = [label for label in available if not _is_audio(label)]
    best = (video or list(available))[0]
    wanted = preference.strip().lower()

    if wanted in _BEST:
        return QualityChoice(best)
    if wanted == "worst":
        return QualityChoice((video or list(available))[-1])
    if wanted in _AUDIO:
        audio = [label for label in available if _is_audio(label)]
        return QualityChoice(audio[0]) if audio else QualityChoice(best, fell_back=True)

    for label in available:  # an exact label, e.g. "720p60"
        if label.lower() == wanted:
            return QualityChoice(label)

    target = _height_and_fps(wanted + "p" if wanted.isdigit() else wanted)
    if target is not None:
        same_height: list[tuple[str, int]] = []
        for label in video:
            parsed = _height_and_fps(label)
            if parsed is not None and parsed[0] == target[0]:
                same_height.append((label, parsed[1]))
        if same_height:  # "720p" with no frame rate → the smoothest 720p on offer
            return QualityChoice(max(same_height, key=lambda item: item[1])[0])
    return QualityChoice(best, fell_back=True)
