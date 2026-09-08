"""Parses EventSub WebSocket messages into small, typed values. Every
message shares the same ``{"metadata": {...}, "payload": {...}}``
envelope; ``message_type`` in metadata says which of the five kinds it
is.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

MessageType = Literal[
    "session_welcome", "session_keepalive", "notification", "session_reconnect", "revocation"
]


@dataclass(frozen=True, slots=True)
class ParsedMessage:
    message_id: str
    message_type: MessageType
    payload: dict[str, Any]
    subscription_type: str | None = None


def parse_message(raw: dict[str, Any]) -> ParsedMessage:
    metadata = raw["metadata"]
    return ParsedMessage(
        message_id=metadata["message_id"],
        message_type=metadata["message_type"],
        payload=raw.get("payload", {}),
        subscription_type=metadata.get("subscription_type"),
    )


def session_id_of(message: ParsedMessage) -> str:
    """Valid for ``session_welcome`` and ``session_reconnect`` — both
    carry a ``payload.session.id``."""
    return message.payload["session"]["id"]


def keepalive_timeout_of(message: ParsedMessage) -> int:
    """Only present on ``session_welcome`` — a reconnect's session block
    doesn't repeat it; the timeout already established stays in effect."""
    return message.payload["session"]["keepalive_timeout_seconds"]


def reconnect_url_of(message: ParsedMessage) -> str:
    return message.payload["session"]["reconnect_url"]


def broadcaster_ref_of(message: ParsedMessage) -> str:
    """The ``broadcaster_user_id`` a ``notification`` or ``revocation``
    concerns. For a ``revocation``, this is nested one level deeper
    (under ``subscription.condition``) than for a ``notification``
    (directly under ``event``)."""
    if message.message_type == "revocation":
        return message.payload["subscription"]["condition"]["broadcaster_user_id"]
    return message.payload["event"]["broadcaster_user_id"]
