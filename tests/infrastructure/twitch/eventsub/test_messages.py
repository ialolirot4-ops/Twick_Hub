from twick_hub.infrastructure.twitch.eventsub.messages import (
    broadcaster_ref_of,
    keepalive_timeout_of,
    parse_message,
    reconnect_url_of,
    session_id_of,
)

_WELCOME = {
    "metadata": {"message_id": "m1", "message_type": "session_welcome", "message_timestamp": "t"},
    "payload": {
        "session": {
            "id": "sess1",
            "status": "connected",
            "keepalive_timeout_seconds": 10,
            "reconnect_url": None,
        }
    },
}

_NOTIFICATION_ONLINE = {
    "metadata": {
        "message_id": "m2",
        "message_type": "notification",
        "message_timestamp": "t",
        "subscription_type": "stream.online",
    },
    "payload": {"event": {"broadcaster_user_id": "123", "type": "live"}},
}

_RECONNECT = {
    "metadata": {"message_id": "m3", "message_type": "session_reconnect", "message_timestamp": "t"},
    "payload": {
        "session": {
            "id": "sess2",
            "status": "reconnecting",
            "reconnect_url": "wss://eventsub.wss.twitch.tv/ws?id=sess2",
        }
    },
}

_REVOCATION = {
    "metadata": {
        "message_id": "m4",
        "message_type": "revocation",
        "message_timestamp": "t",
        "subscription_type": "stream.online",
    },
    "payload": {
        "subscription": {
            "id": "sub1",
            "status": "authorization_revoked",
            "condition": {"broadcaster_user_id": "123"},
        }
    },
}


def test_parse_session_welcome():
    message = parse_message(_WELCOME)
    assert message.message_type == "session_welcome"
    assert session_id_of(message) == "sess1"
    assert keepalive_timeout_of(message) == 10


def test_parse_notification_and_broadcaster_ref():
    message = parse_message(_NOTIFICATION_ONLINE)
    assert message.message_type == "notification"
    assert message.subscription_type == "stream.online"
    assert broadcaster_ref_of(message) == "123"


def test_parse_session_reconnect():
    message = parse_message(_RECONNECT)
    assert session_id_of(message) == "sess2"
    assert reconnect_url_of(message) == "wss://eventsub.wss.twitch.tv/ws?id=sess2"


def test_parse_revocation_and_broadcaster_ref():
    message = parse_message(_REVOCATION)
    assert message.message_type == "revocation"
    assert broadcaster_ref_of(message) == "123"


def test_parse_keepalive():
    keepalive = {
        "metadata": {
            "message_id": "m5",
            "message_type": "session_keepalive",
            "message_timestamp": "t",
        },
        "payload": {},
    }
    message = parse_message(keepalive)
    assert message.message_type == "session_keepalive"
    assert message.payload == {}
