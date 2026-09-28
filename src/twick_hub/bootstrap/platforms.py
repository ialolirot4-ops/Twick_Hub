"""Assembles the real Twitch/Kick ``PlatformAdapters`` (FASE 21c,
docs/risk-register.md RISK-ARCH-01).

FASE 21a registered both platforms with empty ``PlatformAdapters()``; this
module is what fills them in. It's separate from ``build_container()`` on
purpose: Twitch's ``IntegrityAdapter`` is a ``QObject`` that needs a
``QNetworkAccessManager`` (and therefore a live ``QGuiApplication``), while
``build_container()`` is Qt-free and stays that way — ``main()`` builds the
Qt app first, calls ``build_platform_adapters()``, and hands the result to
``build_container(platform_adapters=...)``.

Nothing here talks to the network at construction time: every adapter only
reaches Twitch/Kick when a use case actually calls it.

Not wired here (FASE 21d): Twitch's ``LiveMonitor`` (EventSub needs the
project's Twitch app credentials, which ``AppConfig`` doesn't carry yet)
and Kick's polling monitor.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import httpx
from PySide6.QtNetwork import QNetworkAccessManager

from twick_hub.application.platform_registry import PlatformAdapters
from twick_hub.config.settings import AppConfig
from twick_hub.domain.enums import Platform
from twick_hub.infrastructure.kick.account_service import KickAccountService
from twick_hub.infrastructure.kick.channel_directory import KickChannelDirectory
from twick_hub.infrastructure.kick.client import KickAPIClient
from twick_hub.infrastructure.kick.config import (
    DEFAULT_REDIRECT_HOST,
    DEFAULT_REDIRECT_PATH,
    DEFAULT_REDIRECT_PORT,
    KickAppCredentials,
)
from twick_hub.infrastructure.kick.oauth_flow import KickOAuthFlow
from twick_hub.infrastructure.kick.redirect_listener import LocalHttpRedirectListener
from twick_hub.infrastructure.kick.token_store import KickTokenStore
from twick_hub.infrastructure.twitch.account_service import TwitchAccountService
from twick_hub.infrastructure.twitch.browser_cookie_import import FirefoxCookieImporter
from twick_hub.infrastructure.twitch.channel_directory import TwitchChannelDirectory
from twick_hub.infrastructure.twitch.clip_provider import TwitchClipProvider
from twick_hub.infrastructure.twitch.config import USER_TOKEN_STORE_KEY
from twick_hub.infrastructure.twitch.errors import SecureStorageUnavailableError
from twick_hub.infrastructure.twitch.gql.client import TwitchGQLClient
from twick_hub.infrastructure.twitch.integrity_adapter import (
    IntegrityAdapter,
    IntegrityHeaderSource,
)
from twick_hub.infrastructure.twitch.playback.playback_resolver import TwitchPlaybackResolver
from twick_hub.infrastructure.twitch.token_store import TwitchTokenStore
from twick_hub.infrastructure.twitch.video_provider import TwitchVideoProvider

logger = logging.getLogger(__name__)


def build_platform_adapters(
    config: AppConfig,
    *,
    network_manager: QNetworkAccessManager,
    http_client: httpx.AsyncClient | None = None,
) -> dict[Platform, PlatformAdapters]:
    """One ``httpx.AsyncClient`` is shared by both platforms' adapters
    (independent of the download engine's own client, see
    ``dependencies._build_download_service``). Closing it at shutdown is
    part of RISK-ARCH-09's scope (22.1), same as the download client.
    ``http_client`` is injectable so tests can supply a ``MockTransport``.
    """
    http_client = http_client or httpx.AsyncClient()
    return {
        Platform.TWITCH: _build_twitch(http_client, network_manager),
        Platform.KICK: _build_kick(config, http_client),
    }


def _build_twitch(
    http_client: httpx.AsyncClient, network_manager: QNetworkAccessManager
) -> PlatformAdapters:
    token_store = TwitchTokenStore()
    get_user_token = _twitch_user_token_getter(token_store)

    integrity = IntegrityAdapter(network_manager, get_user_token)
    gql = TwitchGQLClient(http_client, IntegrityHeaderSource(integrity))
    directory = TwitchChannelDirectory(gql)

    return PlatformAdapters(
        account=TwitchAccountService(FirefoxCookieImporter(), token_store, http_client),
        channel_directory=directory,
        # One class implements both — a single GetChannel query already
        # carries the channel's current stream (see channel_directory.py).
        live_stream_provider=directory,
        video_provider=TwitchVideoProvider(gql, directory),
        clip_provider=TwitchClipProvider(gql, directory),
        playback_resolver=TwitchPlaybackResolver(gql, http_client, directory, get_user_token),
    )


def _twitch_user_token_getter(token_store: TwitchTokenStore) -> Callable[[], str | None]:
    """Sync getter shared by ``IntegrityAdapter`` and the playback resolver.

    An unusable OS credential store is reported as "no session" instead of
    raising: ``IntegrityAdapter`` calls this inside a Qt slot right after
    stopping its own timeout, so an exception there would leave the
    awaiting coroutine hanging with nothing left to time it out. The
    warning never includes the token.
    """

    def get_user_token() -> str | None:
        try:
            return token_store.load(USER_TOKEN_STORE_KEY)
        except SecureStorageUnavailableError:
            logger.warning("OS credential store unavailable; treating as no Twitch session.")
            return None

    return get_user_token


def _build_kick(config: AppConfig, http_client: httpx.AsyncClient) -> PlatformAdapters:
    secret = config.kick_client_secret
    credentials = KickAppCredentials(
        client_id=config.kick_client_id,
        client_secret=secret.get_secret_value() if secret is not None else None,
    )
    if not credentials.is_configured:
        # Absence of adapters *is* how a platform says "not supported"
        # (PlatformCapabilities is derived from them, never hardcoded), so
        # an unconfigured Kick doesn't advertise an account it can't connect.
        logger.info(
            "Kick app credentials not set (TWICK_HUB_KICK_CLIENT_ID / "
            "TWICK_HUB_KICK_CLIENT_SECRET); Kick stays without adapters."
        )
        return PlatformAdapters()

    token_store = KickTokenStore()
    oauth = KickOAuthFlow(
        credentials,
        http_client,
        LocalHttpRedirectListener(
            DEFAULT_REDIRECT_HOST, DEFAULT_REDIRECT_PORT, DEFAULT_REDIRECT_PATH
        ),
    )

    def access_token() -> str | None:
        # ``account`` is bound just below; the API client only calls this
        # at request time. KickAccountService.get_access_token exists for
        # exactly this (see its docstring).
        return account.get_access_token()

    api_client = KickAPIClient(http_client, access_token)
    account = KickAccountService(oauth, token_store, api_client)
    directory = KickChannelDirectory(api_client)

    return PlatformAdapters(
        account=account,
        channel_directory=directory,
        live_stream_provider=directory,
    )
