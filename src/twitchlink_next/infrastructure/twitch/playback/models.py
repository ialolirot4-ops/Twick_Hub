"""Playback token models — ported from TwitchLink 3.5.5's
``TwitchGQLModels.py`` (StreamPlaybackAccessToken/VideoPlaybackAccessToken/
ClipPlaybackAccessToken).

The ``token_data`` this reads out of ``value`` is a base64/JSON blob
Twitch's own client also decodes purely to read these same fields
(authorization reason, geoblock) — nothing here verifies or needs to
verify the token's signature; ``signature``+``value`` are sent back to
Twitch as-is when requesting the manifest, and Twitch does its own
verification server-side.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field


def _parse_token_data(value: str) -> dict:
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return {}


@dataclass(frozen=True, slots=True)
class PlaybackToken:
    signature: str
    value: str
    token_data: dict = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "token_data", _parse_token_data(self.value))

    @property
    def forbidden(self) -> bool:
        return bool(self.token_data.get("authorization", {}).get("forbidden"))

    @property
    def forbidden_reason(self) -> str | None:
        return self.token_data.get("authorization", {}).get("reason") if self.forbidden else None

    @property
    def geo_blocked(self) -> bool:
        return bool(self.token_data.get("ci_gb"))

    @property
    def geo_block_reason(self) -> str | None:
        return self.token_data.get("geoblock_reason") if self.geo_blocked else None


def stream_hides_ads(ad_request_handling: dict) -> bool:
    """Ported from ``StreamPlaybackAccessToken.hideAds``: true when this
    specific viewer's account (Turbo, or a subscription with the
    ad-free benefit) means Twitch won't serve them ads at all — a
    partial, verified answer to docs/risk-register.md RISK-TWITCH-02,
    not a full one. It tells us when SSAI ads are definitely not a
    concern for this viewer; it says nothing about what's in the
    segments for a viewer without either.
    """
    try:
        current_user = ad_request_handling["currentUser"]
        user = ad_request_handling["user"]
        if current_user["hasTurbo"]:
            return True
        subscription_benefit = user["self"]["subscriptionBenefit"]
        if subscription_benefit is not None and subscription_benefit["product"]["hasAdFree"]:
            return True
        ad_properties = user["adProperties"]
        return bool(ad_properties["hasPrerollsDisabled"] and ad_properties["hasPostrollsDisabled"])
    except (KeyError, TypeError):
        return False
