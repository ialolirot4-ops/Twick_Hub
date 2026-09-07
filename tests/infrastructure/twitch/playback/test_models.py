import json

from twitchlink_next.infrastructure.twitch.playback.models import PlaybackToken, stream_hides_ads


def _token(payload: dict) -> PlaybackToken:
    return PlaybackToken(signature="sig", value=json.dumps(payload))


def test_token_with_no_restrictions():
    token = _token({"authorization": {"forbidden": False, "reason": None}})
    assert token.forbidden is False
    assert token.forbidden_reason is None
    assert token.geo_blocked is False


def test_token_forbidden_for_subscriber_only():
    token = _token({"authorization": {"forbidden": True, "reason": "UNAUTHORIZED_ENTITLMENTS"}})
    assert token.forbidden is True
    assert token.forbidden_reason == "UNAUTHORIZED_ENTITLMENTS"


def test_token_forbidden_for_another_reason():
    token = _token({"authorization": {"forbidden": True, "reason": "SOME_OTHER_REASON"}})
    assert token.forbidden is True
    assert token.forbidden_reason == "SOME_OTHER_REASON"


def test_token_geo_blocked():
    token = _token(
        {"authorization": {"forbidden": False}, "ci_gb": True, "geoblock_reason": "COPYRIGHT"}
    )
    assert token.geo_blocked is True
    assert token.geo_block_reason == "COPYRIGHT"


def test_token_with_malformed_value_defaults_to_unrestricted():
    token = PlaybackToken(signature="sig", value="not json at all")
    assert token.forbidden is False
    assert token.geo_blocked is False


def test_hides_ads_true_for_turbo():
    data = {"currentUser": {"hasTurbo": True}, "user": {"self": None, "adProperties": None}}
    assert stream_hides_ads(data) is True


def test_hides_ads_true_for_ad_free_subscription_benefit():
    data = {
        "currentUser": {"hasTurbo": False},
        "user": {
            "self": {"subscriptionBenefit": {"product": {"hasAdFree": True}}},
            "adProperties": {"hasPrerollsDisabled": False, "hasPostrollsDisabled": False},
        },
    }
    assert stream_hides_ads(data) is True


def test_hides_ads_false_for_a_regular_viewer():
    data = {
        "currentUser": {"hasTurbo": False},
        "user": {
            "self": {"subscriptionBenefit": None},
            "adProperties": {"hasPrerollsDisabled": False, "hasPostrollsDisabled": False},
        },
    }
    assert stream_hides_ads(data) is False


def test_hides_ads_false_on_missing_or_malformed_data():
    assert stream_hides_ads({}) is False
    assert stream_hides_ads({"currentUser": {}}) is False
