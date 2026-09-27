from __future__ import annotations

import pytest

from twick_hub.application.scheduling.quality import NoQualitiesError, select_quality

TWITCH = ["1080p60", "720p60", "720p30", "480p30", "360p30", "160p30", "audio_only"]


@pytest.mark.parametrize("preference", ["best", "source", "BEST"])
def test_best_is_the_first_video_quality(preference):
    assert select_quality(preference, TWITCH).label == "1080p60"


def test_best_skips_an_audio_entry_listed_first():
    assert select_quality("best", ["audio_only", "720p60"]).label == "720p60"


def test_worst_is_the_lowest_video_quality_not_audio():
    assert select_quality("worst", TWITCH).label == "160p30"


@pytest.mark.parametrize("preference", ["audio-only", "audio_only", "Audio Only"])
def test_audio_only(preference):
    assert select_quality(preference, TWITCH).label == "audio_only"


def test_audio_only_unavailable_falls_back_to_best():
    choice = select_quality("audio-only", ["1080p60", "720p60"])
    assert (choice.label, choice.fell_back) == ("1080p60", True)


def test_an_exact_label_wins():
    assert select_quality("720p30", TWITCH).label == "720p30"


@pytest.mark.parametrize("preference", ["720p", "720"])
def test_a_bare_resolution_picks_its_smoothest_variant(preference):
    assert select_quality(preference, TWITCH).label == "720p60"


def test_an_unavailable_resolution_falls_back_to_best_and_says_so():
    choice = select_quality("1440p", TWITCH)
    assert (choice.label, choice.fell_back) == ("1080p60", True)


def test_a_known_resolution_with_an_unavailable_frame_rate_uses_the_same_height():
    assert select_quality("480p60", TWITCH).label == "480p30"


def test_unparseable_preference_falls_back_to_best():
    choice = select_quality("whatever", TWITCH)
    assert choice.fell_back is True


def test_no_qualities_at_all_is_an_error():
    with pytest.raises(NoQualitiesError):
        select_quality("best", [])
