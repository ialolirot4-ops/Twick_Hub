"""Identity entities: who an account belongs to, and who broadcasts.

Entities are frozen dataclasses — updates go through ``dataclasses.replace``
(or a small helper method where that reads better) rather than in-place
mutation, so a Channel or Favorite handed to one part of the app can't be
silently changed by another.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from twitchlink_next.domain.value_objects import PlatformRef


@dataclass(frozen=True, slots=True)
class User:
    """A generic account on a platform — a clip creator, a chat
    participant, or the person behind a Channel. Deliberately minimal:
    anything broadcast-specific belongs on Channel, not here.
    """

    ref: PlatformRef
    username: str
    display_name: str
    avatar_url: str | None = None


@dataclass(frozen=True, slots=True)
class Channel:
    """A broadcaster's channel — what gets favorited, searched for, and
    shown on the Live page. Wraps the underlying :class:`User` and adds
    the broadcast-specific fields TwitchLink 3.5.5 already tracks
    (docs/migration-map.md's Search/Account sections).
    """

    ref: PlatformRef
    user: User
    is_live: bool = False
    stream_title: str | None = None
    category: str | None = None
    follower_count: int | None = None
    is_verified_or_partner: bool = False


@dataclass(frozen=True, slots=True)
class PlatformAccount:
    """The app's own signed-in identity on a platform — what the Account
    page (FASE 2) shows as connected/not connected. Distinct from
    :class:`User`: a PlatformAccount is *this installation's* login, not
    just any account referenced elsewhere in the domain.

    The OAuth/session token itself is never a field here — it lives in
    the OS keyring (docs/architecture-decisions.md AD-07), not in a domain
    object that could end up logged, serialized, or displayed.
    """

    ref: PlatformRef
    username: str
    connected_at: datetime
    is_connected: bool = True
