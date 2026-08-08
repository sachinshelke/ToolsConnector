"""Integration tests for the desktop OAuth loopback helper.

Uses a real loopback socket and a stdlib (non-httpx) client to simulate the
browser redirect, so respx only intercepts the token exchange.

Done-when: login() drives begin -> loopback catch -> complete end to end and
returns a CredentialSet; the listener captures code and reports error.
"""

from __future__ import annotations

import socket
import threading
import time
import urllib.error
import urllib.request

import pytest
import respx
from httpx import Response

from toolsconnector.runtime.auth import loopback
from toolsconnector.runtime.auth.flows import GOOGLE
from toolsconnector.runtime.auth.loopback import login


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _fire_redirect(port: int, query: str) -> None:
    """Hit the loopback callback via stdlib urllib (bypasses respx), with retry
    until the server is up."""
    url = f"http://127.0.0.1:{port}/?{query}"
    for _ in range(50):
        try:
            urllib.request.urlopen(url, timeout=2).read()  # noqa: S310 -- fixed loopback URL
            return
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.1)


def test_wait_for_callback_captures_code():
    server = loopback._bind_loopback("127.0.0.1", 0)
    port = server.server_address[1]
    threading.Thread(target=_fire_redirect, args=(port, "code=abc&state=st"), daemon=True).start()
    result = loopback._serve_until_redirect(server, timeout=10)
    assert result == {"code": "abc", "state": "st"}


def test_wait_for_callback_reports_error():
    server = loopback._bind_loopback("127.0.0.1", 0)
    port = server.server_address[1]
    threading.Thread(target=_fire_redirect, args=(port, "error=access_denied"), daemon=True).start()
    result = loopback._serve_until_redirect(server, timeout=10)
    assert result["error"] == "access_denied"


@pytest.mark.asyncio
@respx.mock
async def test_login_end_to_end():
    port = _free_port()
    respx.post(GOOGLE.token_url).mock(
        return_value=Response(
            200,
            json={"access_token": "ya29.x", "refresh_token": "1//r", "expires_in": 3600},
        )
    )
    # Simulate the browser hitting the redirect once the listener is up.
    threading.Thread(target=_fire_redirect, args=(port, "code=abc&state=st"), daemon=True).start()

    creds = await login(
        GOOGLE,
        client_id="cid.apps.googleusercontent.com",
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        host="127.0.0.1",
        port=port,
        open_browser=False,
        state="st",
        timeout=10,
    )

    assert creds.access_token == "ya29.x"
    assert creds.refresh_token == "1//r"
    assert creds.token_expiry is not None
