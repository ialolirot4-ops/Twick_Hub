"""Twitch playback resolution — implements
``domain.protocols.PlaybackResolver``.

Deliberately separate from FASE 4b's metadata adapters (this only
resolves *how to play/download* a Media, never looks up channel/video/
clip *metadata*) and from FASE 7's future download engine (this returns
a URL; it never fetches or writes a single byte of video). Master Plan
§40: "Separar: API metadata / Playback / Download."
"""

from __future__ import annotations

from urllib.parse import quote

import httpx

from twick_hub.domain.enums import MediaKind
from twick_hub.domain.protocols import ChannelDirectory
from twick_hub.domain.value_objects import Media, PlaybackSource
from twick_hub.infrastructure.twitch.gql.client import TwitchGQLClient
from twick_hub.infrastructure.twitch.playback import operations as ops
from twick_hub.infrastructure.twitch.playback.errors import (
    ChannelOfflineError,
    GeoBlockedError,
    PlaybackForbiddenError,
    SubscriberOnlyRestrictedError,
)
from twick_hub.infrastructure.twitch.playback.errors import (
    TwitchPlaybackError as _TwitchPlaybackError,  # re-exported for callers
)
from twick_hub.infrastructure.twitch.playback.manifest import (
    VariantStream,
    parse_variant_playlist,
)
from twick_hub.infrastructure.twitch.playback.models import PlaybackToken, stream_hides_ads

_HLS_SERVER = "https://usher.ttvnw.net/api/channel/hls/"
_VOD_SERVER = "https://usher.ttvnw.net/vod/"

__all__ = ["TwitchPlaybackResolver", "NotAuthenticatedError", "_TwitchPlaybackError"]


class NotAuthenticatedError(_TwitchPlaybackError):
    """Every playback operation needs the user's own OAuth token — ported
    from TwitchGQLAPI.py's ``useAuth=True`` on all three. Distinct from
    the auth package's own errors: this is "you're not signed in", not
    "signing in failed".
    """


class TwitchPlaybackResolver:
    def __init__(
        self,
        gql_client: TwitchGQLClient,
        http_client: httpx.AsyncClient,
        channel_directory: ChannelDirectory,
        user_token_getter,
    ) -> None:
        self._client = gql_client
        self._http = http_client
        self._channel_directory = channel_directory
        self._get_user_token = user_token_getter

    async def resolve(self, media: Media, quality: str) -> PlaybackSource:
        variants = await self._variants_for(media)
        chosen = _select_quality(variants, quality)
        return PlaybackSource(url=chosen.url, quality_label=chosen.display_name, bandwidth_bps=None)

    async def available_qualities(self, media: Media) -> list[str]:
        variants = await self._variants_for(media)
        return [variant.display_name for variant in variants]

    async def _variants_for(self, media: Media) -> list[VariantStream]:
        user_token = self._get_user_token()
        if not user_token:
            raise NotAuthenticatedError("Playback requires a connected Twitch account.")

        if media.kind == MediaKind.STREAM:
            return await self._stream_variants(media, user_token)
        if media.kind == MediaKind.VIDEO:
            return await self._video_variants(media, user_token)
        if media.kind == MediaKind.CLIP:
            return await self._clip_variants(media, user_token)
        raise ValueError(f"Unsupported media kind for Twitch playback: {media.kind}")

    async def _stream_variants(self, media: Media, user_token: str) -> list[VariantStream]:
        channel = await self._channel_directory.get_channel(media.channel_ref or media.ref)
        login = channel.user.username

        responses = await self._client.send_persisted_batch(
            [
                (*ops.STREAM_PLAYBACK_ACCESS_TOKEN, ops.stream_token_variables(login)),
                (*ops.STREAM_AD_REQUEST_HANDLING, ops.stream_ad_handling_variables(login)),
            ],
            user_token=user_token,
        )
        token_data = responses[0]["data"]["streamPlaybackAccessToken"]
        if token_data is None:
            raise ChannelOfflineError(login)
        token = PlaybackToken(signature=token_data["signature"], value=token_data["value"])
        _validate_token(token, subject=login)
        # Recorded for future use (e.g. surfacing "ad-free" in the UI) —
        # not acted on here; see models.py's stream_hides_ads docstring.
        stream_hides_ads(responses[1].get("data") or {})

        manifest_url = f"{_HLS_SERVER}{login}.m3u8"
        return await self._fetch_manifest(
            manifest_url, token, offline_error=ChannelOfflineError(login)
        )

    async def _video_variants(self, media: Media, user_token: str) -> list[VariantStream]:
        video_id = media.ref.external_id
        response = await self._client.send_persisted(
            *ops.VIDEO_PLAYBACK_ACCESS_TOKEN,
            ops.video_token_variables(video_id),
            user_token=user_token,
        )
        token_data = response["data"]["videoPlaybackAccessToken"]
        if token_data is None:
            # Ported behavior: 3.5.5 raises VideoNotFound upstream instead.
            raise ChannelOfflineError(video_id)
        token = PlaybackToken(signature=token_data["signature"], value=token_data["value"])
        _validate_token(token, subject=video_id)

        manifest_url = f"{_VOD_SERVER}{video_id}.m3u8"
        return await self._fetch_manifest(
            manifest_url, token, offline_error=ChannelOfflineError(video_id)
        )

    async def _clip_variants(self, media: Media, user_token: str) -> list[VariantStream]:
        slug = media.ref.external_id
        response = await self._client.send_persisted(
            *ops.CLIP_PLAYBACK_ACCESS_TOKEN, ops.clip_token_variables(slug), user_token=user_token
        )
        clip_data = response["data"]["clip"]
        if clip_data is None:
            return []

        signature = clip_data.get("playbackAccessToken", {}).get("signature") or ""
        value = clip_data.get("playbackAccessToken", {}).get("value") or ""
        variants = [
            VariantStream(
                name=f"{quality['quality']}p{quality['frameRate']}",
                group_id=f"{quality['quality']}p{quality['frameRate']}",
                url=f"{quality['sourceURL']}?sig={signature}&token={quote(value)}",
                quality=int(quality["quality"]) if str(quality["quality"]).isdigit() else None,
                frame_rate=round(float(quality["frameRate"])) if quality.get("frameRate") else None,
            )
            for quality in clip_data.get("videoQualities") or []
        ]
        return sorted(variants, key=lambda variant: variant.sort_key, reverse=True)

    async def _fetch_manifest(
        self, url: str, token: PlaybackToken, *, offline_error: Exception
    ) -> list[VariantStream]:
        params = {
            "allow_source": "true",
            "allow_audio_only": "true",
            "sig": token.signature,
            "token": token.value,
            "fast_bread": "true",
            "supported_codecs": "av1,h265,h264",
        }
        response = await self._http.get(url, params=params)
        if response.status_code == 404:
            raise offline_error
        response.raise_for_status()
        variants = parse_variant_playlist(response.text, base_url=str(response.url))
        if not variants:
            raise offline_error
        return variants


def _validate_token(token: PlaybackToken, *, subject: str) -> None:
    """Ported from ``TwitchStreamPlaybackGenerator._validateToken``."""
    if token.forbidden:
        if token.forbidden_reason == "UNAUTHORIZED_ENTITLMENTS":
            raise SubscriberOnlyRestrictedError(subject)
        raise PlaybackForbiddenError(token.forbidden_reason)
    if token.geo_blocked:
        raise GeoBlockedError(token.geo_block_reason)


def _select_quality(variants: list[VariantStream], quality: str) -> VariantStream:
    if not variants:
        raise _TwitchPlaybackError("No playable quality variants were found.")
    if quality in ("best", "source"):
        return variants[0]
    for variant in variants:
        if variant.display_name == quality or variant.group_id == quality:
            return variant
    raise _TwitchPlaybackError(
        f"Quality {quality!r} is not available "
        f"(have: {', '.join(v.display_name for v in variants)})"
    )
