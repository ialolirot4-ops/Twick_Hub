from __future__ import annotations

import pytest

from twick_hub.domain.version import InvalidVersionError, Version


def test_parses_a_plain_version():
    v = Version.parse("1.2.3")
    assert (v.major, v.minor, v.patch, v.prerelease) == (1, 2, 3, None)


def test_parses_a_prerelease_version():
    v = Version.parse("2.0.0-rc1")
    assert v.prerelease == "rc1"


def test_str_round_trips():
    assert str(Version.parse("1.2.3")) == "1.2.3"
    assert str(Version.parse("1.2.3-rc1")) == "1.2.3-rc1"


@pytest.mark.parametrize(
    "text", ["1.2", "1.2.3.4", "v1.2.3", "1.2.x", "", "1.2.3-", "not-a-version"]
)
def test_rejects_malformed_versions(text):
    with pytest.raises(InvalidVersionError):
        Version.parse(text)


def test_patch_ordering():
    assert Version.parse("1.0.0") < Version.parse("1.0.1")
    assert Version.parse("1.0.1") > Version.parse("1.0.0")


def test_minor_and_major_ordering():
    assert Version.parse("1.9.9") < Version.parse("1.10.0")
    assert Version.parse("1.99.0") < Version.parse("2.0.0")


def test_prerelease_sorts_before_its_final_release():
    assert Version.parse("1.0.0-rc1") < Version.parse("1.0.0")
    assert Version.parse("1.0.0") > Version.parse("1.0.0-rc1")


def test_prereleases_of_the_same_version_compare_lexicographically():
    assert Version.parse("1.0.0-alpha") < Version.parse("1.0.0-beta")


def test_equal_versions_are_not_less_than_each_other():
    a, b = Version.parse("1.2.3"), Version.parse("1.2.3")
    assert not (a < b) and not (b < a)
    assert a <= b and a >= b
    assert a == b


def test_prerelease_does_not_affect_equality_of_distinct_versions():
    assert Version.parse("1.2.3") != Version.parse("1.2.4")


# FASE 18 — Testing: ``__gt__`` delegates to ``other < self``, so the
# existing "sorts before its final release" tests above only ever call
# ``__lt__`` with the prerelease on the left. These two pin down the two
# ``__lt__`` branches that only fire with the *final* release on the left.


def test_prerelease_vs_final_ordering_across_different_triples():
    assert Version.parse("1.0.0-rc1") < Version.parse("2.0.0")


def test_final_release_is_never_less_than_a_prerelease_of_the_same_triple():
    assert not (Version.parse("1.0.0") < Version.parse("1.0.0-rc1"))
