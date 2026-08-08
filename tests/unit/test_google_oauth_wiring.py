"""Tests for wiring the Google connectors to the OAuth flow.

Scopes come from each connector's declared spec (single source of truth), not a
duplicated list. Covers scope extraction, the web begin_for() path, a non-OAuth
connector rejection, and an end-to-end login_for() via the loopback.
"""

from __future__ import annotations

import socket
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlparse

import pytest
import respx
from httpx import Response

from toolsconnector.connectors.gdrive import GoogleDrive
from toolsconnector.connectors.gmail import Gmail
from toolsconnector.connectors.stripe import Stripe
from toolsconnector.runtime.auth import (
    GOOGLE,
    begin_for,
    login_for,
    oauth_scopes,
    scopes_for,
)
from toolsconnector.runtime.auth.flows import OAuthFlowError

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.labels",
]


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _fire_redirect(port: int, query: str) -> None:
    url = f"http://127.0.0.1:{port}/?{query}"
    for _ in range(50):
        try:
            urllib.request.urlopen(url, timeout=2).read()  # noqa: S310 -- fixed loopback URL
            return
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.1)


def test_oauth_scopes_come_from_the_connector_spec():
    # Single source of truth: exactly what gmail/connector.py declares.
    assert oauth_scopes(Gmail) == GMAIL_SCOPES


def test_oauth_scopes_rejects_non_oauth_connector():
    with pytest.raises(OAuthFlowError):
        oauth_scopes(Stripe)  # Stripe is basic-auth, no OAuth2 provider


def test_begin_for_applies_connector_scopes_and_google_preset():
    pending = begin_for(Gmail, client_id="cid", redirect_uri="http://127.0.0.1:8765/")
    q = parse_qs(urlparse(pending.authorization_url).query)
    assert q["scope"] == [" ".join(GMAIL_SCOPES)]
    assert q["access_type"] == ["offline"]  # Google preset applied
    assert q["code_challenge_method"] == ["S256"]


def test_begin_for_scopes_override_requests_a_subset():
    only_readonly = ["https://www.googleapis.com/auth/gmail.readonly"]
    pending = begin_for(
        Gmail, client_id="cid", redirect_uri="http://127.0.0.1:8765/", scopes=only_readonly
    )
    q = parse_qs(urlparse(pending.authorization_url).query)
    assert q["scope"] == only_readonly


def test_begin_for_incremental_sets_include_granted_scopes():
    pending = begin_for(
        Gmail, client_id="cid", redirect_uri="http://127.0.0.1:8765/", incremental=True
    )
    q = parse_qs(urlparse(pending.authorization_url).query)
    assert q["include_granted_scopes"] == ["true"]


def test_scopes_for_unions_connectors_without_duplicates():
    combined = scopes_for(Gmail, GoogleDrive)
    # gmail (4) + drive (2), order-preserving, no dupes
    assert combined == oauth_scopes(Gmail) + oauth_scopes(GoogleDrive)
    assert len(combined) == len(set(combined))


@pytest.mark.asyncio
@respx.mock
async def test_login_for_end_to_end():
    port = _free_port()
    respx.post(GOOGLE.token_url).mock(
        return_value=Response(
            200,
            json={"access_token": "ya29.x", "refresh_token": "1//r", "expires_in": 3600},
        )
    )
    threading.Thread(target=_fire_redirect, args=(port, "code=abc&state=st"), daemon=True).start()

    creds = await login_for(
        Gmail,
        client_id="cid.apps.googleusercontent.com",
        host="127.0.0.1",
        port=port,
        open_browser=False,
        state="st",
        timeout=10,
    )

    assert creds.access_token == "ya29.x"
    assert creds.refresh_token == "1//r"
