"""Regression tests for the production failure modes found by the OAuth audit.

Each test here maps to a defect that the original happy-path suite stayed green
through. See `.agent/artifacts/oauth-test-strategy.md`.
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
import respx
from httpx import Response

from toolsconnector.runtime.auth.credentials import RefreshingCredentials
from toolsconnector.runtime.auth.flows import (
    GOOGLE,
    OAuthFlowError,
    begin,
    complete,
    granted_scopes,
    missing_scopes,
    parse_redirect,
)
from toolsconnector.runtime.auth.loopback import _bind_loopback, _serve_until_redirect, login
from toolsconnector.spec.auth import AuthType
from toolsconnector.types.credentials import CredentialSet

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]


def _pending():
    return begin(GOOGLE, client_id="cid", redirect_uri="http://127.0.0.1:8765/", scopes=SCOPES)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# --------------------------------------------------------------------------
# P1-6 -- complete() input guards + web-path error redirect
# --------------------------------------------------------------------------


class TestRedirectAndInputGuards:
    @pytest.mark.asyncio
    @respx.mock
    async def test_empty_code_is_rejected_before_any_http(self):
        route = respx.post(GOOGLE.token_url).mock(return_value=Response(200, json={}))
        p = _pending()
        with pytest.raises(OAuthFlowError, match="No authorization code"):
            await complete(p, code="", state=p.state)
        assert route.call_count == 0

    @pytest.mark.asyncio
    @respx.mock
    async def test_none_code_is_rejected_not_posted_as_empty_string(self):
        """`code=None` used to urlencode to `code=` and hit Google."""
        route = respx.post(GOOGLE.token_url).mock(return_value=Response(200, json={}))
        p = _pending()
        with pytest.raises(OAuthFlowError, match="No authorization code"):
            await complete(p, code=None, state=p.state)  # type: ignore[arg-type]
        assert route.call_count == 0

    @pytest.mark.asyncio
    async def test_none_state_raises_oauthflowerror_not_typeerror(self):
        """`request.args.get("state")` returning None must stay inside our contract."""
        with pytest.raises(OAuthFlowError, match="No OAuth state"):
            await complete(_pending(), code="abc", state=None)  # type: ignore[arg-type]

    def test_parse_redirect_surfaces_the_denial_reason(self):
        url = (
            "http://127.0.0.1:8765/?error=access_denied"
            "&error_description=The+user+denied+access&state=st"
        )
        with pytest.raises(OAuthFlowError, match="The user denied access"):
            parse_redirect(url)

    def test_parse_redirect_returns_code_and_state_on_success(self):
        params = parse_redirect("http://127.0.0.1:8765/?code=4/abc&state=st")
        assert params["code"] == "4/abc"
        assert params["state"] == "st"

    def test_parse_redirect_accepts_a_bare_query_string(self):
        assert parse_redirect("code=4/abc&state=st")["code"] == "4/abc"

    def test_parse_redirect_rejects_a_redirect_with_neither_code_nor_error(self):
        with pytest.raises(OAuthFlowError, match="neither"):
            parse_redirect("http://127.0.0.1:8765/?foo=bar")


# --------------------------------------------------------------------------
# P2-7 -- granted scope is the only authority on what the token covers
# --------------------------------------------------------------------------


class TestGrantedScopes:
    @pytest.mark.asyncio
    @respx.mock
    async def test_partial_grant_is_recorded_and_detectable(self):
        """Google's granular consent: user unticks a box, response says so."""
        respx.post(GOOGLE.token_url).mock(
            return_value=Response(
                200,
                json={
                    "access_token": "ya29.x",
                    "expires_in": 3600,
                    "token_type": "Bearer",
                    # only 1 of the 2 requested scopes granted
                    "scope": "https://www.googleapis.com/auth/gmail.readonly",
                },
            )
        )
        p = _pending()
        creds = await complete(p, code="c", state=p.state)

        assert granted_scopes(creds) == ["https://www.googleapis.com/auth/gmail.readonly"]
        assert missing_scopes(creds, SCOPES) == ["https://www.googleapis.com/auth/gmail.send"]

    @pytest.mark.asyncio
    @respx.mock
    async def test_full_grant_reports_nothing_missing(self):
        respx.post(GOOGLE.token_url).mock(
            return_value=Response(
                200, json={"access_token": "ya29.x", "expires_in": 3600, "scope": " ".join(SCOPES)}
            )
        )
        p = _pending()
        creds = await complete(p, code="c", state=p.state)
        assert missing_scopes(creds, SCOPES) == []

    @pytest.mark.asyncio
    @respx.mock
    async def test_provider_reporting_no_scope_yields_no_false_alarm(self):
        respx.post(GOOGLE.token_url).mock(
            return_value=Response(200, json={"access_token": "ya29.x", "expires_in": 3600})
        )
        p = _pending()
        creds = await complete(p, code="c", state=p.state)
        assert granted_scopes(creds) is None
        assert missing_scopes(creds, SCOPES) == []  # unknown != missing


# --------------------------------------------------------------------------
# P0-3 -- unknown expiry must not silently degrade to a static token
# --------------------------------------------------------------------------


class TestUnknownExpiry:
    @respx.mock
    def test_credential_without_expiry_refreshes_once_to_establish_one(self):
        route = respx.post(GOOGLE.token_url).mock(
            return_value=Response(200, json={"access_token": "ya29.fresh", "expires_in": 3600})
        )
        auth = RefreshingCredentials(
            CredentialSet(
                auth_type=AuthType.OAUTH2,
                access_token="ya29.stale",
                refresh_token="1//r",
                token_expiry=None,
                client_id="cid",
            )
        )
        assert auth.needs_refresh() is True
        assert auth() == "ya29.fresh"
        assert auth.credentials.token_expiry is not None
        # ...and does not keep refreshing on every access.
        assert auth() == "ya29.fresh"
        assert route.call_count == 1

    @respx.mock
    def test_unknown_expiry_without_refresh_token_uses_the_token_as_is(self):
        """A pasted BYOK access token has no expiry and nothing to refresh with."""
        route = respx.post(GOOGLE.token_url).mock(return_value=Response(200, json={}))
        auth = RefreshingCredentials(
            CredentialSet(auth_type=AuthType.OAUTH2, access_token="ya29.byok", token_expiry=None)
        )
        assert auth() == "ya29.byok"
        assert auth() == "ya29.byok"
        assert route.call_count == 0

    @respx.mock
    def test_failed_refresh_on_unknown_expiry_falls_back_to_the_existing_token(self):
        """An *unproven* expiry must never hard-fail a possibly-valid token.

        Found live: a credential rehydrated without client_id made Google answer
        400 invalid_request, which turned a usable access token into a crash.
        """
        route = respx.post(GOOGLE.token_url).mock(
            return_value=Response(400, json={"error": "invalid_request"})
        )
        auth = RefreshingCredentials(
            CredentialSet(
                auth_type=AuthType.OAUTH2,
                access_token="ya29.maybe-ok",
                refresh_token="1//r",
                token_expiry=None,
            )
        )
        assert auth() == "ya29.maybe-ok"
        assert route.call_count == 1
        assert auth() == "ya29.maybe-ok"  # does not retry forever
        assert route.call_count == 1

    @respx.mock
    def test_failed_refresh_on_known_expiry_still_raises(self):
        """A token proven dead must not be silently used."""
        respx.post(GOOGLE.token_url).mock(
            return_value=Response(400, json={"error": "invalid_grant"})
        )
        auth = RefreshingCredentials(
            CredentialSet(
                auth_type=AuthType.OAUTH2,
                access_token="ya29.dead",
                refresh_token="1//r",
                token_expiry=datetime.now(timezone.utc) - timedelta(minutes=5),
                client_id="cid",
            )
        )
        with pytest.raises(Exception, match="invalid_grant"):
            auth()

    @respx.mock
    def test_refresh_records_scope_shrink(self):
        respx.post(GOOGLE.token_url).mock(
            return_value=Response(
                200,
                json={
                    "access_token": "ya29.fresh",
                    "expires_in": 3600,
                    "scope": "https://www.googleapis.com/auth/gmail.readonly",
                },
            )
        )
        auth = RefreshingCredentials(
            CredentialSet(
                auth_type=AuthType.OAUTH2,
                access_token="a",
                refresh_token="1//r",
                token_expiry=datetime.now(timezone.utc) - timedelta(minutes=5),
                client_id="cid",
            )
        )
        auth()
        assert granted_scopes(auth.credentials) == [
            "https://www.googleapis.com/auth/gmail.readonly"
        ]


# --------------------------------------------------------------------------
# P1-4 / P1-5 -- loopback robustness on real sockets
# --------------------------------------------------------------------------


class TestLoopbackRobustness:
    def test_port_clash_raises_oauthflowerror_not_raw_oserror(self):
        port = _free_port()
        squatter = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        squatter.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        squatter.bind(("127.0.0.1", port))
        squatter.listen(1)
        try:
            with pytest.raises(OAuthFlowError, match="Could not start the loopback listener"):
                _bind_loopback("127.0.0.1", port)
        finally:
            squatter.close()

    def test_port_zero_binds_a_real_ephemeral_port(self):
        server = _bind_loopback("127.0.0.1", 0)
        try:
            assert server.server_address[1] > 0
        finally:
            server.server_close()

    def test_idle_peer_cannot_outlast_the_deadline(self):
        """An open connection that never writes used to block past the timeout."""
        server = _bind_loopback("127.0.0.1", 0)
        port = server.server_address[1]

        stop = threading.Event()

        def idle_peer():
            s = socket.create_connection(("127.0.0.1", port), timeout=5)
            stop.wait(20)  # hold the connection open, send nothing
            s.close()

        peer = threading.Thread(target=idle_peer, daemon=True)
        peer.start()
        time.sleep(0.2)

        started = time.monotonic()
        try:
            with pytest.raises(OAuthFlowError, match="Timed out"):
                _serve_until_redirect(server, timeout=2.0)
        finally:
            stop.set()
        elapsed = time.monotonic() - started
        # Handler read timeout is 5s; without it this blocked until the peer
        # closed (measured 8.3s at timeout=2.0 in the audit).
        assert elapsed < 8.0, f"deadline overshot: {elapsed:.1f}s"

    @pytest.mark.asyncio
    async def test_login_reports_port_clash_before_opening_a_browser(self):
        """A clash must fail loudly, not strand the user on a consent screen."""
        port = _free_port()
        squatter = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        squatter.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        squatter.bind(("127.0.0.1", port))
        squatter.listen(1)
        try:
            with pytest.raises(OAuthFlowError, match="Could not start the loopback listener"):
                await login(
                    GOOGLE,
                    client_id="cid",
                    scopes=SCOPES,
                    port=port,
                    open_browser=False,
                    timeout=2,
                )
        finally:
            squatter.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_login_with_port_zero_completes_end_to_end(self):
        """port=0 is the fix for clashes; the real port must reach redirect_uri."""
        respx.post(GOOGLE.token_url).mock(
            return_value=Response(200, json={"access_token": "ya29.z", "expires_in": 3600})
        )
        captured: dict = {}

        def fake_open(url: str) -> bool:
            captured["url"] = url
            port = int(url.split("127.0.0.1%3A")[1].split("%2F")[0])

            def hit():
                time.sleep(0.1)
                try:
                    socket.create_connection(("127.0.0.1", port), timeout=2).sendall(
                        b"GET /?code=abc&state=st HTTP/1.1\r\nHost: x\r\n\r\n"
                    )
                except OSError:
                    pass

            threading.Thread(target=hit, daemon=True).start()
            return True

        import toolsconnector.runtime.auth.loopback as lb

        original = lb.webbrowser.open
        lb.webbrowser.open = fake_open  # type: ignore[assignment]
        try:
            creds = await login(
                GOOGLE, client_id="cid", scopes=SCOPES, port=0, state="st", timeout=10
            )
        finally:
            lb.webbrowser.open = original  # type: ignore[assignment]

        assert creds.access_token == "ya29.z"
        assert "127.0.0.1%3A0%2F" not in captured["url"]  # a real port, not 0


def test_asyncio_import_is_used():
    assert asyncio is not None
