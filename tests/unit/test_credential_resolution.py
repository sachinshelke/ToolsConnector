"""Credential resolution: OAuth output must reach the wire as a usable token.

These are the tests that close the gap between "the flow returns a CredentialSet"
and "the connector sends a working Authorization header". Each asserts on the
BYTES A CONNECTOR WOULD SEND, not on an intermediate object.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx
from httpx import Response

from toolsconnector.connectors.gmail import Gmail
from toolsconnector.errors import RefreshFailedError, TokenExpiredError
from toolsconnector.runtime.auth.credentials import RefreshingCredentials
from toolsconnector.runtime.auth.flows import GOOGLE
from toolsconnector.spec.auth import AuthType
from toolsconnector.types.credentials import CredentialSet, resolve_credential


def _oauth_creds(**over):
    base = {
        "auth_type": AuthType.OAUTH2,
        "access_token": "ya29.live",
        "refresh_token": "1//refresh",
        "token_expiry": datetime.now(timezone.utc) + timedelta(hours=1),
        "client_id": "cid",
        "client_secret": "sec",
    }
    base.update(over)
    return CredentialSet(**base)


class TestResolution:
    def test_credentialset_narrows_to_access_token(self):
        assert resolve_credential(_oauth_creds()) == "ya29.live"

    def test_plain_string_passes_through_unchanged(self):
        # BYOK behaviour for the other 70+ connectors must not change.
        assert resolve_credential("xoxb-plain-token") == "xoxb-plain-token"
        assert resolve_credential(None) is None
        assert resolve_credential({"a": 1}) == {"a": 1}

    def test_callable_is_invoked_as_a_token_provider(self):
        assert resolve_credential(lambda: "from-my-vault") == "from-my-vault"

    def test_callable_returning_credentialset_is_resolved_recursively(self):
        assert resolve_credential(lambda: _oauth_creds()) == "ya29.live"

    def test_bearer_and_api_key_types_narrow_correctly(self):
        bearer = CredentialSet(auth_type=AuthType.BEARER_TOKEN, bearer_token="tok")
        api = CredentialSet(auth_type=AuthType.API_KEY, api_key="key")
        basic = CredentialSet(auth_type=AuthType.BASIC, username="u", password="p")
        assert resolve_credential(bearer) == "tok"
        assert resolve_credential(api) == "key"
        assert resolve_credential(basic) == "u:p"


class TestConnectorSendsRealToken:
    """The end of the chain: what actually goes out on the wire."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_credentialset_reaches_gmail_authorization_header(self):
        """Passing the OAuth flow's output straight to a connector must work.

        Before credential resolution this sent the stringified pydantic model,
        i.e. `Authorization: Bearer auth_type=<AuthType.OAUTH2...`.
        """
        route = respx.get("https://gmail.googleapis.com/gmail/v1/users/me/profile").mock(
            return_value=Response(200, json={"emailAddress": "a@b.c", "messagesTotal": 1})
        )
        gmail = Gmail(credentials=_oauth_creds())
        await gmail._request("GET", "/users/me/profile")

        sent = route.calls.last.request.headers["Authorization"]
        assert sent == "Bearer ya29.live"
        assert "CredentialSet" not in sent
        assert "auth_type" not in sent

    @pytest.mark.asyncio
    @respx.mock
    async def test_token_provider_callable_is_re_read_each_request(self):
        """A rotating token must be picked up without rebuilding the connector."""
        respx.get("https://gmail.googleapis.com/gmail/v1/users/me/profile").mock(
            return_value=Response(200, json={"emailAddress": "a@b.c"})
        )
        tokens = iter(["first-token", "second-token"])
        gmail = Gmail(credentials=lambda: next(tokens))

        await gmail._request("GET", "/users/me/profile")
        await gmail._request("GET", "/users/me/profile")

        route = respx.routes[0]
        assert route.calls[0].request.headers["Authorization"] == "Bearer first-token"
        assert route.calls[1].request.headers["Authorization"] == "Bearer second-token"


class TestRefreshingCredentials:
    @respx.mock
    def test_expired_token_is_refreshed_and_new_one_is_returned(self):
        respx.post(GOOGLE.token_url).mock(
            return_value=Response(200, json={"access_token": "ya29.fresh", "expires_in": 3600})
        )
        auth = RefreshingCredentials(
            _oauth_creds(token_expiry=datetime.now(timezone.utc) - timedelta(minutes=5))
        )
        assert auth.needs_refresh() is True
        assert auth() == "ya29.fresh"
        assert auth.needs_refresh() is False

    @respx.mock
    def test_valid_token_does_not_hit_the_network(self):
        route = respx.post(GOOGLE.token_url).mock(return_value=Response(200, json={}))
        auth = RefreshingCredentials(_oauth_creds())
        assert auth() == "ya29.live"
        assert route.call_count == 0

    @respx.mock
    def test_rotated_refresh_token_is_handed_back_via_on_refresh(self):
        """TC stores nothing -- rotation must reach the caller or it is lost."""
        respx.post(GOOGLE.token_url).mock(
            return_value=Response(
                200,
                json={
                    "access_token": "ya29.fresh",
                    "refresh_token": "1//ROTATED",
                    "expires_in": 3600,
                },
            )
        )
        saved: list = []
        auth = RefreshingCredentials(
            _oauth_creds(token_expiry=datetime.now(timezone.utc) - timedelta(minutes=5)),
            on_refresh=saved.append,
        )
        auth()
        assert saved and saved[-1].refresh_token == "1//ROTATED"
        assert auth.credentials.refresh_token == "1//ROTATED"

    @respx.mock
    def test_expired_without_refresh_token_raises_actionable_error(self):
        auth = RefreshingCredentials(
            _oauth_creds(
                refresh_token=None,
                token_expiry=datetime.now(timezone.utc) - timedelta(minutes=5),
            )
        )
        with pytest.raises(TokenExpiredError, match="re-run the OAuth flow"):
            auth()

    @respx.mock
    def test_invalid_grant_surfaces_as_refresh_failed(self):
        """Google's real revoked/expired-refresh-token response, not an ideal one."""
        respx.post(GOOGLE.token_url).mock(
            return_value=Response(
                400,
                json={
                    "error": "invalid_grant",
                    "error_description": "Token has been expired or revoked.",
                },
            )
        )
        auth = RefreshingCredentials(
            _oauth_creds(token_expiry=datetime.now(timezone.utc) - timedelta(minutes=5))
        )
        with pytest.raises(RefreshFailedError, match="invalid_grant"):
            auth()

    @respx.mock
    def test_html_error_page_does_not_crash_with_json_decode_error(self):
        """Proxies/outages return HTML; the error must still be actionable."""
        respx.post(GOOGLE.token_url).mock(
            return_value=Response(200, html="<html><body>502 Bad Gateway</body></html>")
        )
        auth = RefreshingCredentials(
            _oauth_creds(token_expiry=datetime.now(timezone.utc) - timedelta(minutes=5))
        )
        with pytest.raises(RefreshFailedError, match="non-JSON"):
            auth()

    @pytest.mark.asyncio
    @respx.mock
    async def test_arefresh_keeps_the_event_loop_free(self):
        respx.post(GOOGLE.token_url).mock(
            return_value=Response(200, json={"access_token": "ya29.async", "expires_in": 3600})
        )
        auth = RefreshingCredentials(
            _oauth_creds(token_expiry=datetime.now(timezone.utc) - timedelta(minutes=5))
        )
        updated = await auth.arefresh()
        assert updated.access_token == "ya29.async"
        assert auth() == "ya29.async"  # already fresh -> no blocking call

    @pytest.mark.asyncio
    @respx.mock
    async def test_connector_keeps_working_past_expiry(self):
        """The whole point: a long-lived connector survives the 1-hour cliff."""
        respx.post(GOOGLE.token_url).mock(
            return_value=Response(200, json={"access_token": "ya29.renewed", "expires_in": 3600})
        )
        api = respx.get("https://gmail.googleapis.com/gmail/v1/users/me/profile").mock(
            return_value=Response(200, json={"emailAddress": "a@b.c"})
        )
        auth = RefreshingCredentials(
            _oauth_creds(token_expiry=datetime.now(timezone.utc) - timedelta(minutes=5))
        )
        gmail = Gmail(credentials=auth)

        await gmail._request("GET", "/users/me/profile")

        assert api.calls.last.request.headers["Authorization"] == "Bearer ya29.renewed"


def test_httpx_is_imported_for_type_use_only():
    """Guard against accidentally removing the httpx import used by refresh."""
    assert httpx is not None
