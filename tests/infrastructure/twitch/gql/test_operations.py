from twitchlink_next.infrastructure.twitch.gql.operations import GET_CHANNEL, GET_VIDEO


def test_build_payload_includes_only_declared_variables():
    payload = GET_VIDEO.build_payload({"id": "123", "unrelated": "ignored"})
    assert payload["variables"] == {"id": "123"}
    assert payload["query"] == GET_VIDEO.query


def test_build_payload_fills_missing_variables_with_none():
    payload = GET_CHANNEL.build_payload({"login": "northernlion"})
    assert payload["variables"] == {"id": None, "login": "northernlion"}
