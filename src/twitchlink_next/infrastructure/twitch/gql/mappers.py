"""Maps raw GQL response dicts to Domain entities.

This module is the actual boundary Master Plan §39 means by "No mezclar
API con Domain": everything above this file works with plain dicts and
Twitch's own field names (``displayName``, ``lengthSeconds``, ...);
everything below/after it only ever sees ``twitchlink_next.domain``
types. No Domain module imports anything from here — the dependency
points one way.
"""

from __future__ import annotations

from datetime import datetime

from twitchlink_next.domain.content import Clip, Stream, Video
from twitchlink_next.domain.enums import Platform
from twitchlink_next.domain.identity import Channel, User
from twitchlink_next.domain.value_objects import Duration, PlatformRef

_DEFAULT_DATETIME = "0001-01-01T00:00:00Z"


def _parse_datetime(value: str | None) -> datetime:
    return datetime.fromisoformat(value or _DEFAULT_DATETIME)


def _user_ref(data: dict) -> PlatformRef:
    return PlatformRef(platform=Platform.TWITCH, external_id=str(data["id"]))


_UNKNOWN_OWNER_REF = PlatformRef(platform=Platform.TWITCH, external_id="0")


def _owner_ref(owner: dict) -> PlatformRef:
    return _user_ref(owner) if owner else _UNKNOWN_OWNER_REF


def map_user(data: dict) -> User:
    login = data.get("login") or ""
    return User(
        ref=_user_ref(data),
        username=login,
        display_name=data.get("displayName") or login,
        avatar_url=data.get("profileImageURL") or None,
    )


def map_channel(data: dict) -> Channel:
    roles = data.get("roles") or {}
    followers = data.get("followers") or {}
    stream_data = data.get("stream")

    return Channel(
        ref=_user_ref(data),
        user=map_user(data),
        is_live=stream_data is not None,
        stream_title=stream_data.get("title") if stream_data else None,
        category=(stream_data.get("game") or {}).get("name") if stream_data else None,
        follower_count=followers.get("totalCount"),
        is_verified_or_partner=bool(roles.get("isPartner") or roles.get("isAffiliate")),
    )


def map_stream(data: dict, channel_ref: PlatformRef) -> Stream | None:
    """``data`` is the ``user`` dict from a GetChannel response — this
    reads its nested ``stream`` field (or returns None if the channel is
    offline), rather than needing a separate request. Matches how the
    ported query already embeds stream data in the channel lookup.
    """
    stream_data = data.get("stream")
    if stream_data is None:
        return None

    return Stream(
        ref=PlatformRef(platform=Platform.TWITCH, external_id=str(stream_data["id"])),
        channel_ref=channel_ref,
        title=stream_data.get("title") or "",
        category=(stream_data.get("game") or {}).get("name"),
        started_at=_parse_datetime(stream_data.get("createdAt")),
        viewer_count=stream_data.get("viewersCount") or 0,
        thumbnail_url=stream_data.get("previewImageURL") or None,
    )


def map_video(data: dict) -> Video:
    owner = data.get("owner") or {}
    return Video(
        ref=PlatformRef(platform=Platform.TWITCH, external_id=str(data["id"])),
        channel_ref=_owner_ref(owner),
        title=data.get("title") or "",
        published_at=_parse_datetime(data.get("publishedAt") or data.get("createdAt")),
        duration=Duration(int(data.get("lengthSeconds") or 0)),
        view_count=data.get("viewCount") or 0,
        # Not derivable from this metadata query — Twitch only reveals
        # subscriber-only restriction when resolving playback (FASE 4c).
        # docs/functional-baseline.md already flags this for
        # confirmation there rather than assuming a value here.
        is_subscriber_only=False,
        thumbnail_url=data.get("previewThumbnailURL") or None,
    )


def map_clip(data: dict) -> Clip:
    broadcaster = data.get("broadcaster") or {}
    curator = data.get("curator") or broadcaster
    clip_id = data.get("id") or data.get("slug")
    return Clip(
        ref=PlatformRef(platform=Platform.TWITCH, external_id=str(clip_id)),
        channel_ref=_owner_ref(broadcaster),
        title=data.get("title") or "",
        creator=map_user(curator),
        created_at=_parse_datetime(data.get("createdAt")),
        duration=Duration(int(data.get("durationSeconds") or 0)),
        view_count=data.get("viewCount") or 0,
        thumbnail_url=data.get("thumbnailURL") or None,
    )
