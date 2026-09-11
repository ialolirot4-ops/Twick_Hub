"""Catches the OAuth redirect (``?code=...&state=...``) on a local,
one-shot HTTP listener — the standard approach for a native/desktop app
(RFC 8252), and what Kick's own docs recommend (``localhost`` redirect
URI, not a custom URI scheme).

``RedirectListener`` is a narrow Protocol so tests can inject a fake that
returns a canned ``(code, state)`` pair immediately, instead of a real
server waiting on a real browser round-trip.
"""

from __future__ import annotations

import asyncio
import http.server
import threading
import urllib.parse
from typing import Protocol


class RedirectListener(Protocol):
    async def wait_for_callback(self, timeout: float) -> tuple[str, str]:
        """Returns ``(code, state)`` once the redirect arrives."""
        ...


class LocalHttpRedirectListener:
    def __init__(self, host: str, port: int, path: str) -> None:
        self._host = host
        self._port = port
        self._path = path

    async def wait_for_callback(self, timeout: float = 120) -> tuple[str, str]:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[tuple[str, str]] = loop.create_future()
        expected_path = self._path

        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler's own naming)
                parsed = urllib.parse.urlparse(self.path)
                params = urllib.parse.parse_qs(parsed.query)
                self.send_response(200 if parsed.path == expected_path else 404)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<html><body>You can close this window.</body></html>")
                if parsed.path == expected_path and not future.done():
                    code = params.get("code", [""])[0]
                    state = params.get("state", [""])[0]
                    loop.call_soon_threadsafe(future.set_result, (code, state))

            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                pass  # don't spam stderr with access logs for a one-shot local listener

        server = http.server.HTTPServer((self._host, self._port), _Handler)
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            server.server_close()
