import pytest

from twitchlink_next.domain.enums import Platform
from twitchlink_next.domain.value_objects import Duration, FilenameTemplate, PlatformRef


def test_platform_ref_rejects_empty_external_id():
    with pytest.raises(ValueError, match="external_id"):
        PlatformRef(platform=Platform.TWITCH, external_id="")


def test_platform_ref_equality_is_by_value():
    a = PlatformRef(platform=Platform.TWITCH, external_id="123")
    b = PlatformRef(platform=Platform.TWITCH, external_id="123")
    c = PlatformRef(platform=Platform.KICK, external_id="123")
    assert a == b
    assert a != c


@pytest.mark.parametrize(
    ("total_seconds", "expected"),
    [
        (45, "0:45"),
        (125, "2:05"),
        (3661, "1:01:01"),
    ],
)
def test_duration_formatting(total_seconds, expected):
    assert Duration(total_seconds).formatted == expected


def test_duration_rejects_negative():
    with pytest.raises(ValueError, match="negative"):
        Duration(-1)


def test_filename_template_renders_every_token():
    template = FilenameTemplate("{channel}/{title} ({date})")
    values = {"channel": "northernlion", "title": "Part 12", "date": "2026-09-05"}
    rendered = template.render(values)
    assert rendered == "northernlion/Part 12 (2026-09-05)"


def test_filename_template_raises_on_unknown_token():
    template = FilenameTemplate("{channel}/{missing}")
    with pytest.raises(KeyError, match="missing"):
        template.render({"channel": "northernlion"})
