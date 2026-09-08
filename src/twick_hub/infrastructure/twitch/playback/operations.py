"""Persisted-query definitions for Twitch's playback-access-token
operations, ported verbatim from TwitchLink 3.5.5's ``TwitchGQLConfig.py``
/ ``TwitchGQLAPI.py`` (docs/migration-map.md). These are ordinary
persisted-query hashes — publicly known and used the same way across the
whole ecosystem of Twitch player/downloader tools (streamlink, yt-dlp,
and TwitchLink itself); they identify a query server-side, they aren't a
secret or a bypass of anything.

Unlike FASE 4b's metadata operations, every one of these needs both
Client-Integrity **and** the user's own OAuth token — ported exactly from
TwitchGQLAPI.py's ``useIntegrity=True, useAuth=True`` on all three.
"""

from __future__ import annotations

STREAM_PLAYBACK_ACCESS_TOKEN = (
    "PlaybackAccessToken",
    "ed230aa1e33e07eebb8928504583da78a5173989fadfb1ac94be06a04f3cdbe9",
)
STREAM_AD_REQUEST_HANDLING = (
    "AdRequestHandling",
    "61a5ecca6da3d924efa9dbde811e051b8a10cb6bd0fe22c372c2f4401f3e88d1",
)
VIDEO_PLAYBACK_ACCESS_TOKEN = STREAM_PLAYBACK_ACCESS_TOKEN  # same operation, different variables
CLIP_PLAYBACK_ACCESS_TOKEN = (
    "VideoAccessToken_Clip",
    "4f35f1ac933d76b1da008c806cd5546a7534dfaff83e033a422a81f24e5991b3",
)


def stream_token_variables(login: str) -> dict[str, object]:
    return {
        "login": login,
        "isLive": True,
        "vodID": "",
        "isVod": False,
        "playerType": "embed",
        "platform": "",
    }


def stream_ad_handling_variables(login: str) -> dict[str, object]:
    return {
        "login": login,
        "isLive": True,
        "vodID": "",
        "isVOD": False,
        "isCollection": False,
        "collectionID": "",
    }


def video_token_variables(video_id: str) -> dict[str, object]:
    return {
        "login": "",
        "isLive": False,
        "vodID": video_id,
        "isVod": True,
        "playerType": "embed",
        "platform": "",
    }


def clip_token_variables(slug: str) -> dict[str, object]:
    return {"slug": slug, "platform": ""}
