"""Maps raw Kick API response dicts to Domain entities — same
API/Domain boundary role as ``infrastructure/twitch/gql/mappers.py``
(docs/architecture-decisions.md AD-19).

Channel/Livestream field names come from the official ``kick-api`` Rust
crate's own documented structs (fetched during this phase, with an
example JSON response matching field-for-field) — high confidence.
``map_user`` is the one exception: no single, fully-confirmed
``/public/v1/users`` response example was found during this phase's
research, only that the endpoint exists and returns the caller's own
user under ``data[0]``. It's written defensively (every field via
``.get()``, sane fallbacks) and should be checked against one real
response before FASE 5's account flow ships — flagged here rather than
asserted with false confidence (Master Plan permanent rule: no asumir).
"""

from __future__ import annotations

from datetime import datetime

from twick_hub.domain.content import Stream
from twick_hub.domain.enums import Platform
from twick_hub.domain.identity import Channel, User
from twick_hub.domain.value_objects import PlatformRef


def _ref(broadcaster_user_id: object) -> PlatformRef:
    return PlatformRef(platform=Platform.KICK, external_id=str(broadcaster_user_id))


def map_user(data: dict) -> User:
    user_id = data.get("user_id") or data.get("id")
    name = data.get("name") or data.get("username") or ""
    return User(
        ref=PlatformRef(platform=Platform.KICK, external_id=str(user_id)),
        username=name,
        display_name=name,
        avatar_url=data.get("profile_picture"),
    )


def map_channel(data: dict) -> Channel:
    ref = _ref(data["broadcaster_user_id"])
    slug = data.get("slug", "")
    category = data.get("category") or {}
    return Channel(
        ref=ref,
        user=User(ref=ref, username=slug, display_name=slug, avatar_url=data.get("banner_picture")),
        is_live=data.get("stream") is not None,
        stream_title=data.get("stream_title"),
        category=category.get("name"),
        follower_count=None,  # not present on the Channel resource itself
        is_verified_or_partner=False,  # not exposed by the official API — never guessed
    )


def map_live_stream(data: dict) -> Stream:
    category = data.get("category") or {}
    ref = _ref(data["broadcaster_user_id"])
    return Stream(
        ref=ref,
        channel_ref=ref,
        title=data.get("stream_title") or "",
        category=category.get("name"),
        started_at=datetime.fromisoformat(data["started_at"]),
        viewer_count=data.get("viewer_count") or 0,
        thumbnail_url=data.get("thumbnail"),
    )
