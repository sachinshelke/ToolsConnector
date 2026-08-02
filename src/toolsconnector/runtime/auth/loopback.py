"""Desktop / CLI OAuth loopback helper -- opt-in convenience over the flow core.

Ties :func:`~toolsconnector.runtime.auth.flows.begin` + a throwaway localhost
callback listener + :func:`~toolsconnector.runtime.auth.flows.complete` into a
single call for CLI / desktop / notebook / agent use::

    import asyncio
    from toolsconnector.runtime.auth import GOOGLE, login

    creds = asyncio.run(login(GOOGLE, client_id="...apps.googleusercontent.com",
                              scopes=["https://www.googleapis.com/auth/gmail.readonly"]))

This is the ONLY piece of the OAuth flow that touches a socket; the core
(``flows.py``) stays socket-free. The listener binds to loopback only, handles
exactly one authorization redirect, serves a "you can close this tab" page, and
shuts down -- the same pattern as ``gh auth login`` / ``gcloud auth login``. No
public URL, no hosted server.
"""

from __future__ import annotations

import asyncio
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Optional, cast
from urllib.parse import parse_qs, urlparse

from toolsconnector.types.credentials import CredentialSet

from .flows import OAuthFlowError, ProviderPreset, begin, complete

_SUCCESS_HTML = (
    b"<!doctype html><meta charset=utf-8>"
    b"<body style='font-family:system-ui;text-align:center;padding-top:3rem'>"
    b"<h2>Authorized \xe2\x9c\x93</h2><p>You can close this tab and return to your terminal.</p>"
)
_ERROR_HTML = (
    b"<!doctype html><meta charset=utf-8>"
    b"<body style='font-family:system-ui;text-align:center;padding-top:3rem'>"
    b"<h2>Authorization failed</h2><p>You can close this tab and return to your terminal.</p>"
)


class _LoopbackServer(HTTPServer):
    """One-shot loopback server that stashes the parsed redirect query."""

    result: Optional[dict[str, str]] = None


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 -- stdlib requires the uppercase name
        query = parse_qs(urlparse(self.path).query)
        # Ignore stray hits (e.g. favicon) that carry neither code nor error so
        # the one-shot wait isn't consumed by them.
        if "code" not in query and "error" not in query:
            self.send_response(404)
            self.end_headers()
            return

        cast("_LoopbackServer", self.server).result = {k: v[0] for k, v in query.items()}
        ok = "code" in query

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(_SUCCESS_HTML if ok else _ERROR_HTML)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 -- name fixed by stdlib override
        pass  # silence stdlib stderr logging


def _wait_for_callback(host: str, port: int, timeout: float) -> dict[str, str]:
    """Serve loopback requests until the authorization redirect arrives.

    Binds to *host* (loopback only) and returns the parsed query dict of the
    first request carrying ``code`` or ``error``.

    Raises:
        OAuthFlowError: If no redirect arrives within *timeout* seconds.
    """
    server = _LoopbackServer((host, port), _CallbackHandler)
    server.timeout = 1.0
    deadline = time.monotonic() + timeout
    try:
        while server.result is None and time.monotonic() < deadline:
            server.handle_request()
    finally:
        server.server_close()

    if server.result is None:
        raise OAuthFlowError("Timed out waiting for the OAuth authorization redirect.")
    return server.result


async def login(
    preset: ProviderPreset,
    *,
    client_id: str,
    scopes: list[str],
    client_secret: Optional[str] = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
    state: Optional[str] = None,
    timeout: float = 180.0,
) -> CredentialSet:
    """Run the full desktop OAuth dance and return a :class:`CredentialSet`.

    Opens the browser to the provider's consent screen, catches the redirect on
    ``http://{host}:{port}/`` (register this as the client's redirect URI), and
    exchanges the code for tokens.

    Args:
        preset: Provider preset (e.g. :data:`~toolsconnector.runtime.auth.flows.GOOGLE`).
        client_id: OAuth client id.
        scopes: Scopes to request.
        client_secret: Set for Google "Desktop app" clients (non-confidential);
            omit for pure public clients.
        host: Loopback bind address; defaults to ``127.0.0.1``.
        port: Loopback port; must match the registered redirect URI.
        open_browser: If ``False`` (or if opening fails), print the URL instead.
        state: Optional CSRF state; generated if omitted.
        timeout: Seconds to wait for the redirect before giving up.

    Returns:
        A :class:`CredentialSet` ready for ``OAuth2Provider`` / ``KeyStore``.

    Raises:
        OAuthFlowError: On denial, state mismatch, timeout, or token error.
    """
    redirect_uri = f"http://{host}:{port}/"
    pending = begin(
        preset,
        client_id=client_id,
        redirect_uri=redirect_uri,
        scopes=scopes,
        state=state,
    )

    opened = webbrowser.open(pending.authorization_url) if open_browser else False
    if not opened:
        print(f"Open this URL to authorize:\n\n  {pending.authorization_url}\n")

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _wait_for_callback, host, port, timeout)

    if "error" in result:
        detail = result.get("error_description") or result["error"]
        raise OAuthFlowError(f"Authorization was denied: {detail}")

    return await complete(
        pending,
        code=result["code"],
        state=result.get("state", ""),
        client_secret=client_secret,
    )
