from __future__ import annotations

from pathlib import Path

import pytest

from twick_hub.application.scheduling.destination import (
    DEFAULT_TEMPLATE,
    DestinationPlanner,
    sanitize_component,
)
from twick_hub.application.scheduling.retry import RetryPolicy

_VALUES = {"channel": "streamer", "title": "Big Stream", "date": "2026-09-21"}


def _planner(existing: set[Path] | None = None, template: str = DEFAULT_TEMPLATE):
    existing = existing or set()
    return DestinationPlanner(Path("/rec"), template, exists=lambda p: p in existing)


def test_default_template_makes_a_channel_folder():
    assert _planner().plan(_VALUES) == str(Path("/rec/streamer/Big Stream (2026-09-21).mp4"))


def test_directory_and_extension_overrides():
    path = _planner().plan(_VALUES, directory="/other", extension="MKV")
    assert path == str(Path("/other/streamer/Big Stream (2026-09-21).mkv"))


def test_extension_is_cleaned():
    assert _planner().plan(_VALUES, extension="../x").endswith(".x")
    assert _planner().plan(_VALUES, extension="").endswith(".mp4")


def test_a_taken_name_gets_a_counter_from_disk_and_from_reserved():
    first = Path("/rec/streamer/Big Stream (2026-09-21).mp4")
    second = Path("/rec/streamer/Big Stream (2026-09-21) (2).mp4")

    assert _planner({first}).plan(_VALUES) == str(second)
    assert _planner().plan(_VALUES, reserved=[str(first), str(second)]).endswith("(3).mp4")


def test_hostile_values_cannot_add_path_components():
    values = {**_VALUES, "title": "../../etc/passwd", "channel": "a/b\\c"}

    path = Path(_planner().plan(values))

    assert path.parent.parent == Path("/rec")  # exactly channel folder + file, nothing escaped
    assert ".." not in path.parts


def test_template_slashes_still_make_subfolders():
    path = _planner(template="{channel}/{date}/{title}").plan(_VALUES)
    assert path == str(Path("/rec/streamer/2026-09-21/Big Stream.mp4"))


def test_missing_template_token_is_a_clear_error():
    with pytest.raises(KeyError, match="game"):
        _planner(template="{game}/{title}").plan(_VALUES)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('a<b>c:d"e|f?g*h', "a_b_c_d_e_f_g_h"),
        ("  trailing dots... ", "trailing dots"),
        ("", "_"),
        ("..", "_"),
        ("CON", "_CON"),
        ("nul.txt", "_nul.txt"),
        ("x" * 300, "x" * 100),
        ("tab\tand\nnewline", "tab_and_newline"),
    ],
)
def test_sanitize_component(raw, expected):
    assert sanitize_component(raw) == expected


def test_retry_policy_backs_off_and_caps():
    policy = RetryPolicy(base_delay_seconds=30, factor=2, max_delay_seconds=100)
    assert [policy.delay_for(n) for n in (0, 1, 2, 3, 4)] == [0.0, 30, 60, 100, 100]
