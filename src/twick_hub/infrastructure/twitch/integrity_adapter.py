"""Client-Integrity token adapter.

Ported from TwitchLink 3.5.5's ``IntegrityGenerator.py``
(docs/migration-map.md), adapted to PySide6 and to this project's
dependency-injection style (no ``App.Instance``). The mechanism itself is
unchanged and is worth being explicit about: this does **not** compute or
forge an integrity token. It loads Twitch's own account page in a hidden
``QWebEnginePage``, lets Twitch's own unmodified JavaScript run, and
intercepts the real network request that JavaScript makes to
``INTEGRITY_URL`` — capturing the headers Twitch's own client-side code
already generated — then replays that exact request itself (adding the
user's OAuth token) instead of letting the hidden page's own request go
through. The anti-bot computation happens entirely inside Twitch's own
code, executed by a real Chromium engine; this only captures and reuses
its output.

**Verification status (honest, not assumed):** importing ``QtWebEngineCore``
and constructing a ``QWebEngineProfile`` both work in the sandbox this
phase was built in. Actually loading ``ACCOUNT_PAGE_URL`` and capturing a
real token could not be verified here — Twitch's domains aren't reachable
from this sandbox's network allowlist, and Chromium additionally refuses
to run its renderer as root without ``--no-sandbox`` (confirmed by a real
error when constructing a profile: ``Running as root without --no-sandbox
is not supported``). This needs to be exercised on a real desktop with a
real Twitch session before FASE 4d depends on it — see
docs/risk-register.md RISK-TWITCH-04, which already expected this
component to need ongoing, hands-on maintenance.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from dataclasses import dataclass

from PySide6 import QtCore, QtNetwork, QtWebEngineCore

from twick_hub.infrastructure.twitch.config import ACCOUNT_PAGE_URL, INTEGRITY_URL
from twick_hub.infrastructure.twitch.errors import IntegrityUnavailableError

_TIMEOUT_MS = 15_000


@dataclass(frozen=True, slots=True)
class IntegrityToken:
    headers: dict[str, str]
    value: str
    expires_at: float  # time.time()-based: Twitch's `expiration` is a unix timestamp

    def is_valid(self) -> bool:
        return time.time() < self.expires_at


class _IntegrityRequestInterceptor(QtWebEngineCore.QWebEngineUrlRequestInterceptor):
    """Blocks Twitch's own Integrity POST from actually going out, and
    reports the headers it would have sent."""

    intercepted = QtCore.Signal(dict)

    def interceptRequest(self, info: QtWebEngineCore.QWebEngineUrlRequestInfo) -> None:
        if (
            info.requestUrl().toString() == INTEGRITY_URL
            and bytes(info.requestMethod().data()).decode(errors="ignore") == "POST"
        ):
            info.block(True)
            headers = {
                bytes(key.data()).decode(errors="ignore"): bytes(value.data()).decode(
                    errors="ignore"
                )
                for key, value in info.httpHeaders().items()
            }
            self.intercepted.emit(headers)


class IntegrityAdapter(QtCore.QObject):
    """One adapter instance per running app — owned by whatever
    Infrastructure/bootstrap composition constructs it (never a module-level
    singleton; see docs/architecture-decisions.md AD-03).
    """

    def __init__(
        self,
        network_access_manager: QtNetwork.QNetworkAccessManager,
        user_token_getter: Callable[[], str | None],
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._network = network_access_manager
        self._get_user_token = user_token_getter
        self._cached: IntegrityToken | None = None

    def has_valid_integrity(self) -> bool:
        return self._cached is not None and self._cached.is_valid()

    def get_integrity(self, callback: Callable[[IntegrityToken | None], None]) -> None:
        """Async by callback (matching the original's pattern) rather than
        a coroutine: the work here is driven by Qt's own signal/slot
        machinery (page loads, network replies), not by an awaitable.
        """
        if self.has_valid_integrity():
            callback(self._cached)
            return
        self._begin_capture(callback)

    def _begin_capture(self, callback: Callable[[IntegrityToken | None], None]) -> None:
        profile = QtWebEngineCore.QWebEngineProfile(self)
        interceptor = _IntegrityRequestInterceptor(profile)
        profile.setUrlRequestInterceptor(interceptor)
        page = QtWebEngineCore.QWebEnginePage(profile, self)

        timeout_timer = QtCore.QTimer(self)
        timeout_timer.setSingleShot(True)
        timeout_timer.setInterval(_TIMEOUT_MS)

        def _cleanup() -> None:
            timeout_timer.stop()
            page.deleteLater()
            profile.deleteLater()

        def _on_timeout() -> None:
            _cleanup()
            callback(None)

        def _on_intercepted(headers: dict) -> None:
            timeout_timer.stop()
            user_token = self._get_user_token()
            if user_token:
                headers = {**headers, "Authorization": f"OAuth {user_token}"}

            request = QtNetwork.QNetworkRequest(QtCore.QUrl(INTEGRITY_URL))
            for key, value in headers.items():
                request.setRawHeader(key.encode(), value.encode())
            request.setHeader(
                QtNetwork.QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json"
            )
            reply = self._network.post(request, b"")

            def _on_reply_finished() -> None:
                _cleanup()
                if reply.error() != QtNetwork.QNetworkReply.NetworkError.NoError:
                    callback(None)
                    return
                try:
                    data = json.loads(bytes(reply.readAll().data()).decode(errors="ignore"))
                    token = IntegrityToken(
                        headers=headers, value=data["token"], expires_at=data["expiration"]
                    )
                except (json.JSONDecodeError, KeyError):
                    callback(None)
                    return
                self._cached = token
                callback(token)

            reply.finished.connect(_on_reply_finished)

        timeout_timer.timeout.connect(_on_timeout)
        interceptor.intercepted.connect(_on_intercepted)
        timeout_timer.start()
        page.load(QtCore.QUrl(ACCOUNT_PAGE_URL))

    async def get_integrity_async(self) -> IntegrityToken:
        """Coroutine wrapper around ``get_integrity`` for callers in the
        (async) Application layer — bridges Qt's callback style to
        asyncio without blocking the event loop.
        """
        loop = asyncio.get_running_loop()
        future: asyncio.Future[IntegrityToken | None] = loop.create_future()

        def _callback(token: IntegrityToken | None) -> None:
            if not future.done():
                loop.call_soon_threadsafe(future.set_result, token)

        self.get_integrity(_callback)
        result = await future
        if result is None:
            raise IntegrityUnavailableError(
                "Twitch did not return a valid Client-Integrity token "
                "(timed out, or Twitch changed how it's issued — see "
                "docs/risk-register.md RISK-TWITCH-04)."
            )
        return result
