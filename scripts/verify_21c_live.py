"""FASE 21c — live verification of the real Twitch/Kick adapters.

Run this on a real machine with network access to twitch.tv / kick.com
(the AI sandbox 21a-21b were built in has neither). It goes through the
same ``build_platform_adapters()`` wiring ``main()`` uses, so a PASS here
means the app's real composition works, not a lookalike.

    python scripts/verify_21c_live.py                  # every step
    python scripts/verify_21c_live.py twitch-integrity # just one
    python scripts/verify_21c_live.py --help

Steps, in the order ``all`` runs them:

    twitch-account    import the Firefox session, validate it with Twitch
    twitch-channel    look a channel up through the GQL client
    twitch-integrity  capture a Client-Integrity token (hidden QWebEngine
                      page) and use it: list the channel's videos
    twitch-playback   available qualities of a *live* channel (needs the
                      account step first; SKIPs if the channel is offline)
    kick-connect      OAuth 2.1 + PKCE in your browser (interactive)
    kick-refresh      force the stored token to look expired, then confirm
                      ``current_account()`` refreshes it instead of signing out
    kick-channel      look a channel up through the Kick API

Not part of ``all`` (they sign you out): ``twitch-disconnect``,
``kick-disconnect``.

Kick needs your registered app's credentials, from the environment or a
git-ignored ``.env`` in the directory you run this from:

    TWICK_HUB_KICK_CLIENT_ID=...
    TWICK_HUB_KICK_CLIENT_SECRET=...

and the app's redirect URI must be exactly
``http://localhost:51823/callback``.

This script never prints tokens, cookies or the client secret: it prints
what each step found (usernames, counts, header *names*) and scrubs any
known secret from error text before showing it. Still read the output
before pasting it anywhere.
"""

from __future__ import annotations

import argparse
import asyncio
import platform
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import httpx
import qasync
from PySide6 import __version__ as pyside_version
from PySide6.QtGui import QGuiApplication
from PySide6.QtNetwork import QNetworkAccessManager

from twick_hub.application.platform_registry import PlatformAdapters
from twick_hub.bootstrap.platforms import build_platform_adapters
from twick_hub.config.settings import AppConfig, load_config
from twick_hub.domain.enums import MediaKind, Platform
from twick_hub.domain.identity import Channel
from twick_hub.domain.protocols import AccountProvider
from twick_hub.domain.value_objects import Media
from twick_hub.infrastructure.kick.config import TOKEN_STORE_KEY as KICK_TOKEN_KEY
from twick_hub.infrastructure.kick.token_store import KickTokenStore, StoredKickTokens
from twick_hub.infrastructure.twitch.account_service import TwitchAccountService
from twick_hub.infrastructure.twitch.browser_cookie_import import (
    BrowserProfile,
    CookieImporter,
    FirefoxCookieImporter,
)
from twick_hub.infrastructure.twitch.config import USER_TOKEN_STORE_KEY as TWITCH_TOKEN_KEY
from twick_hub.infrastructure.twitch.token_store import TwitchTokenStore

_ALL_STEPS = (
    "twitch-account",
    "twitch-channel",
    "twitch-integrity",
    "twitch-playback",
    "kick-connect",
    "kick-refresh",
    "kick-channel",
)
_EXTRA_STEPS = ("twitch-disconnect", "kick-disconnect")


# --- output, with scrubbing ---------------------------------------------------


def _known_secrets(config: AppConfig) -> list[str]:
    secrets: list[str] = []
    if config.kick_client_secret is not None:
        secrets.append(config.kick_client_secret.get_secret_value())
    try:
        twitch_token = TwitchTokenStore().load(TWITCH_TOKEN_KEY)
        if twitch_token:
            secrets.append(twitch_token)
    except Exception:  # a broken credential store is reported by the step itself
        pass
    try:
        kick_tokens = KickTokenStore().load(KICK_TOKEN_KEY)
        if kick_tokens is not None:
            secrets.extend([kick_tokens.access_token, kick_tokens.refresh_token])
    except Exception:
        pass
    return [s for s in secrets if s]


@dataclass
class Report:
    config: AppConfig
    lines: list[tuple[str, str, str]] = field(default_factory=list)

    def scrub(self, text: str) -> str:
        for secret in _known_secrets(self.config):
            text = text.replace(secret, "[REDACTED]")
        return text

    def add(self, step: str, status: str, detail: str) -> None:
        detail = self.scrub(detail)
        self.lines.append((step, status, detail))
        print(f"[{status}] {step}: {detail}", flush=True)

    def passed(self, step: str, detail: str) -> None:
        self.add(step, "PASS", detail)

    def failed(self, step: str, detail: str) -> None:
        self.add(step, "FAIL", detail)

    def skipped(self, step: str, detail: str) -> None:
        self.add(step, "SKIP", detail)

    @property
    def any_failed(self) -> bool:
        return any(status == "FAIL" for _, status, _ in self.lines)


# --- steps ---------------------------------------------------------------------


@dataclass
class Context:
    report: Report
    twitch: PlatformAdapters
    kick: PlatformAdapters
    http_client: httpx.AsyncClient
    twitch_channel: str
    kick_channel: str
    firefox_profile: int | None
    channel: Channel | None = None  # set by twitch-channel, reused by later steps
    channel_attempted: bool = False  # twitch-channel already ran (and reported) once


class _OneProfileImporter:
    """Picks a specific Firefox profile — ``TwitchAccountService.connect``
    always takes the first one, which may not be the profile that's logged
    in to Twitch (choosing among several is a UI concern, FASE 4a)."""

    def __init__(self, inner: CookieImporter, index: int) -> None:
        self._inner = inner
        self._index = index

    def list_profiles(self) -> list[BrowserProfile]:
        profiles = self._inner.list_profiles()
        return [profiles[self._index]] if 0 <= self._index < len(profiles) else []

    def import_session_token(self, profile: BrowserProfile) -> str:
        return self._inner.import_session_token(profile)


async def twitch_account(ctx: Context) -> None:
    step = "twitch-account"
    profiles = FirefoxCookieImporter().list_profiles()
    if not profiles:
        ctx.report.failed(step, "no Firefox profile found (is Firefox installed and used?)")
        return
    listing = ", ".join(f"[{i}] {p.display_name}" for i, p in enumerate(profiles))
    print(f"      Firefox profiles: {listing}")

    service: AccountProvider | None
    if ctx.firefox_profile is not None:
        service = TwitchAccountService(
            _OneProfileImporter(FirefoxCookieImporter(), ctx.firefox_profile),
            TwitchTokenStore(),
            ctx.http_client,
        )
    else:
        service = ctx.twitch.account
    assert service is not None
    account = await service.connect()
    ctx.report.passed(step, f"session imported and validated: {account.username}")

    current = await service.current_account()
    if current is None:
        ctx.report.failed(step, "connect() worked but current_account() came back empty")
    else:
        ctx.report.passed(
            step, f"current_account() re-validates the stored token: {current.username}"
        )


async def twitch_channel(ctx: Context) -> None:
    step = "twitch-channel"
    ctx.channel_attempted = True
    directory = ctx.twitch.channel_directory
    assert directory is not None
    channel = await directory.find_channel(ctx.twitch_channel)
    if channel is None:
        ctx.report.failed(step, f"no channel found for {ctx.twitch_channel!r}")
        return
    ctx.channel = channel
    ctx.report.passed(
        step,
        f"{channel.user.display_name} (login {channel.user.username}), "
        f"live={channel.is_live}, followers={channel.follower_count}",
    )


async def _need_channel(ctx: Context, step: str) -> Channel | None:
    if ctx.channel is None and not ctx.channel_attempted:
        await twitch_channel(ctx)
    if ctx.channel is None:
        ctx.report.skipped(step, "needs twitch-channel to succeed first")
    return ctx.channel


async def twitch_integrity(ctx: Context) -> None:
    step = "twitch-integrity"
    channel = await _need_channel(ctx, step)
    if channel is None:
        return
    provider = ctx.twitch.video_provider
    assert provider is not None
    print("      (opens a hidden Chromium page; allow up to ~15 s)", flush=True)
    videos = await provider.list_videos(channel.ref)
    ctx.report.passed(step, f"Integrity token captured and accepted; {len(videos)} video(s) listed")


async def twitch_playback(ctx: Context) -> None:
    step = "twitch-playback"
    channel = await _need_channel(ctx, step)
    if channel is None:
        return
    live = ctx.twitch.live_stream_provider
    resolver = ctx.twitch.playback_resolver
    assert live is not None and resolver is not None
    stream = await live.get_live_stream(channel.ref)
    if stream is None:
        ctx.report.skipped(
            step, f"{channel.user.username} is offline; retry with --twitch-channel <a live one>"
        )
        return
    media = Media(kind=MediaKind.STREAM, ref=channel.ref, title="verify_21c_live")
    qualities = await resolver.available_qualities(media)
    ctx.report.passed(step, f"qualities: {', '.join(qualities) or '(none)'}")


async def kick_connect(ctx: Context) -> None:
    step = "kick-connect"
    account = ctx.kick.account
    if account is None:
        ctx.report.skipped(
            step,
            "Kick not configured (set TWICK_HUB_KICK_CLIENT_ID / TWICK_HUB_KICK_CLIENT_SECRET)",
        )
        return
    print(
        "      Your browser will open; authorize the app within 120 s. "
        "Redirect URI must be http://localhost:51823/callback",
        flush=True,
    )
    connected = await account.connect()
    ctx.report.passed(step, f"OAuth completed: {connected.username}")


async def kick_refresh(ctx: Context) -> None:
    step = "kick-refresh"
    account = ctx.kick.account
    if account is None:
        ctx.report.skipped(step, "Kick not configured")
        return
    store = KickTokenStore()
    tokens = store.load(KICK_TOKEN_KEY)
    if tokens is None:
        ctx.report.skipped(step, "no stored Kick session; run kick-connect first")
        return
    old_access = tokens.access_token
    store.save(
        KICK_TOKEN_KEY,
        StoredKickTokens(
            access_token=tokens.access_token, refresh_token=tokens.refresh_token, expires_at=0.0
        ),
    )
    current = await account.current_account()
    after = store.load(KICK_TOKEN_KEY)
    if current is None or after is None:
        ctx.report.failed(step, "expired token was NOT refreshed (session was cleared)")
    elif after.access_token == old_access or after.expires_at <= time.time():
        ctx.report.failed(step, "account resolved but the stored token was not renewed")
    else:
        ctx.report.passed(step, f"expired token refreshed; still signed in as {current.username}")


async def kick_channel(ctx: Context) -> None:
    step = "kick-channel"
    directory = ctx.kick.channel_directory
    if directory is None:
        ctx.report.skipped(step, "Kick not configured")
        return
    channel = await directory.find_channel(ctx.kick_channel)
    if channel is None:
        ctx.report.failed(step, f"no channel found for {ctx.kick_channel!r}")
        return
    ctx.report.passed(step, f"{channel.user.username}, live={channel.is_live}")


async def twitch_disconnect(ctx: Context) -> None:
    account = ctx.twitch.account
    assert account is not None
    await account.disconnect()
    ctx.report.passed("twitch-disconnect", "signed out and removed the stored token")


async def kick_disconnect(ctx: Context) -> None:
    account = ctx.kick.account
    if account is None:
        ctx.report.skipped("kick-disconnect", "Kick not configured")
        return
    await account.disconnect()
    ctx.report.passed("kick-disconnect", "token revoked and removed")


_STEP_FUNCS: dict[str, Callable[[Context], Awaitable[None]]] = {
    "twitch-account": twitch_account,
    "twitch-channel": twitch_channel,
    "twitch-integrity": twitch_integrity,
    "twitch-playback": twitch_playback,
    "kick-connect": kick_connect,
    "kick-refresh": kick_refresh,
    "kick-channel": kick_channel,
    "twitch-disconnect": twitch_disconnect,
    "kick-disconnect": kick_disconnect,
}


async def _run(ctx: Context, steps: list[str], *, verbose: bool) -> None:
    for step in steps:
        try:
            await _STEP_FUNCS[step](ctx)
        except Exception as error:
            detail = f"{type(error).__name__}: {error}"
            if verbose:
                import traceback

                detail += "\n" + "".join(traceback.format_exception(error))
            ctx.report.failed(step, detail)


# --- entry ---------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="FASE 21c live verification")
    parser.add_argument(
        "steps", nargs="*", choices=[*_ALL_STEPS, *_EXTRA_STEPS, "all"], default=["all"]
    )
    parser.add_argument("--twitch-channel", default="twitch", help="Twitch login (default: twitch)")
    parser.add_argument("--kick-channel", default="xqc", help="Kick slug (default: xqc)")
    parser.add_argument(
        "--firefox-profile", type=int, default=None, help="index from the profile listing"
    )
    parser.add_argument("--verbose", action="store_true", help="show tracebacks on FAIL")
    args = parser.parse_args()
    steps: list[str] = list(_ALL_STEPS) if "all" in args.steps else list(args.steps)

    config = load_config()
    qt_app = QGuiApplication(sys.argv)  # same order as main(): Qt first
    http_client = httpx.AsyncClient()
    adapters = build_platform_adapters(
        config, network_manager=QNetworkAccessManager(), http_client=http_client
    )
    report = Report(config)
    ctx = Context(
        report=report,
        twitch=adapters[Platform.TWITCH],
        kick=adapters[Platform.KICK],
        http_client=http_client,
        twitch_channel=args.twitch_channel,
        kick_channel=args.kick_channel,
        firefox_profile=args.firefox_profile,
    )

    print(
        f"FASE 21c live verification | Python {platform.python_version()} | "
        f"PySide6 {pyside_version} | {platform.system()} {platform.release()}"
    )
    kick_configured = config.kick_client_id is not None and config.kick_client_secret is not None
    print(f"Kick app credentials configured: {kick_configured}")

    loop = qasync.QEventLoop(qt_app)
    asyncio.set_event_loop(loop)
    with loop:
        loop.run_until_complete(_run(ctx, steps, verbose=args.verbose))
        loop.run_until_complete(http_client.aclose())

    print("\n=== summary ===")
    for step, status, _ in report.lines:
        print(f"{status:4}  {step}")
    return 1 if report.any_failed else 0


if __name__ == "__main__":
    sys.exit(main())
