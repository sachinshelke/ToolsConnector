"""Unit tests for toolsconnector.runtime.auth.flows (OAuth acquisition).

Done-when: begin() builds a Google auth URL carrying offline access + consent +
PKCE(S256) + scopes; complete() exchanges the code for a CredentialSet with a
refresh token, sending code_verifier and NO client_secret for a public client;
a mismatched state is rejected before any token request.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
import respx
from httpx import Response

from toolsconnector.runtime.auth.flows import GOOGLE, OAuthFlowError, begin, complete
from toolsconnector.spec.auth import AuthType

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]


def _begin():
    return begin(
        GOOGLE,
        client_id="cid.apps.googleusercontent.com",
        redirect_uri="http://localhost:8765/callback",
        scopes=GMAIL_SCOPES,
    )


def test_begin_builds_google_authorization_url():
    pending = _begin()
    assert pending.authorization_url.startswith(GOOGLE.auth_url + "?")
    q = parse_qs(urlparse(pending.authorization_url).query)

    assert q["response_type"] == ["code"]
    # Google-critical: no refresh token without these two.
    assert q["access_type"] == ["offline"]
    assert q["prompt"] == ["consent"]
    # PKCE
    assert q["code_challenge_method"] == ["S256"]
    assert q["code_challenge"][0]  # present + non-empty
    assert pending.code_verifier  # kept for the exchange
    # passthrough
    assert q["client_id"] == ["cid.apps.googleusercontent.com"]
    assert q["redirect_uri"] == ["http://localhost:8765/callback"]
    assert q["scope"] == [" ".join(GMAIL_SCOPES)]
    assert q["state"] == [pending.state]


@pytest.mark.asyncio
@respx.mock
async def test_complete_exchanges_code_for_credentials():
    pending = _begin()
    route = respx.post(GOOGLE.token_url).mock(
        return_value=Response(
            200,
            json={
                "access_token": "ya29.new",
                "refresh_token": "1//refresh",
                "expires_in": 3600,
            },
        )
    )

    creds = await complete(pending, code="auth-code", state=pending.state)

    assert creds.auth_type == AuthType.OAUTH2
    assert creds.access_token == "ya29.new"
    assert creds.refresh_token == "1//refresh"
    assert creds.token_expiry is not None

    body = route.calls.last.request.content.decode()
    assert "grant_type=authorization_code" in body
    assert "code_verifier=" in body
    assert "code=auth-code" in body
    # public client -> PKCE only, no secret on the wire
    assert "client_secret" not in body


@pytest.mark.asyncio
@respx.mock
async def test_complete_sends_secret_for_confidential_client():
    pending = _begin()
    route = respx.post(GOOGLE.token_url).mock(
        return_value=Response(200, json={"access_token": "ya29.x", "expires_in": 3600})
    )

    await complete(pending, code="c", state=pending.state, client_secret="shh")

    assert "client_secret=shh" in route.calls.last.request.content.decode()


@pytest.mark.asyncio
async def test_complete_rejects_state_mismatch():
    pending = _begin()
    with pytest.raises(OAuthFlowError):
        await complete(pending, code="x", state="not-the-state")
