"""401 classification against Google's REAL response (P0-2).

The bodies and headers below were captured verbatim from
``gmail.googleapis.com/gmail/v1/users/me/profile`` on 2026-08-03 by sending a
deliberately invalid bearer token:

    httpx.get(URL, headers={"Authorization": "Bearer not-a-real-token"})

That matters: Google's 401 body contains **no** expiry marker, so body-only
classification can never distinguish a dead token from a wrong one. The signal
lives in the RFC 6750 challenge header.
"""

from __future__ import annotations

import httpx
import pytest

from toolsconnector.connectors._helpers.http_errors import raise_typed_for_status
from toolsconnector.errors import InvalidCredentialsError, TokenExpiredError

# Verbatim capture -- do not "tidy" this; its exact shape is the point.
GOOGLE_401_BODY = {
    "error": {
        "code": 401,
        "message": (
            "Request had invalid authentication credentials. Expected OAuth 2 access token, "
            "login cookie or other valid authentication credential. See "
            "https://developers.google.com/identity/sign-in/web/devconsole-project."
        ),
        "errors": [
            {
                "message": "Invalid Credentials",
                "domain": "global",
                "reason": "authError",
                "location": "Authorization",
                "locationType": "header",
            }
        ],
        "status": "UNAUTHENTICATED",
    }
}
GOOGLE_401_HEADERS = {
    "WWW-Authenticate": 'Bearer realm="https://accounts.google.com/", error="invalid_token"'
}


def _raise(status=401, json=None, headers=None):
    response = httpx.Response(
        status,
        json=json if json is not None else GOOGLE_401_BODY,
        headers=headers or {},
        request=httpx.Request("GET", "https://gmail.googleapis.com/gmail/v1/users/me/profile"),
    )
    raise_typed_for_status(response, connector="gmail")


def test_google_body_alone_carries_no_expiry_marker():
    """Documents *why* the header is needed: the body says nothing about expiry."""
    with pytest.raises(InvalidCredentialsError) as exc:
        _raise(headers={})
    assert not isinstance(exc.value, TokenExpiredError)


def test_real_google_401_maps_to_token_expired_via_www_authenticate():
    """The whole point of P0-2: reactive re-auth becomes reachable."""
    with pytest.raises(TokenExpiredError) as exc:
        _raise(headers=GOOGLE_401_HEADERS)
    assert exc.value.upstream_status == 401
    assert "invalid_token" in str(exc.value)


def test_token_expired_is_still_caught_as_invalid_credentials():
    """Backward compatibility for the 23 test files / 79 connectors that catch the parent."""
    with pytest.raises(InvalidCredentialsError):
        _raise(headers=GOOGLE_401_HEADERS)
    assert issubclass(TokenExpiredError, InvalidCredentialsError)


def test_token_expired_is_retry_eligible_so_recovery_is_not_short_circuited():
    with pytest.raises(TokenExpiredError) as exc:
        _raise(headers=GOOGLE_401_HEADERS)
    assert exc.value.retry_eligible is True


def test_other_bearer_errors_do_not_become_token_expired():
    """`insufficient_scope` / `invalid_request` are not "get a new token"."""
    with pytest.raises(InvalidCredentialsError) as exc:
        _raise(headers={"WWW-Authenticate": 'Bearer error="insufficient_scope"'})
    assert not isinstance(exc.value, TokenExpiredError)


def test_missing_www_authenticate_keeps_previous_behaviour():
    with pytest.raises(InvalidCredentialsError) as exc:
        _raise(json={"error": {"code": 401, "message": "Unauthorized"}}, headers={})
    assert not isinstance(exc.value, TokenExpiredError)


def test_body_expiry_marker_still_wins_without_a_header():
    with pytest.raises(TokenExpiredError):
        _raise(json={"error": "token_expired"}, headers={})


def test_header_without_error_code_is_ignored():
    with pytest.raises(InvalidCredentialsError) as exc:
        _raise(headers={"WWW-Authenticate": 'Bearer realm="https://accounts.google.com/"'})
    assert not isinstance(exc.value, TokenExpiredError)


def test_unquoted_error_code_is_still_parsed():
    """Not all providers quote the value."""
    with pytest.raises(TokenExpiredError):
        _raise(headers={"WWW-Authenticate": "Bearer error=invalid_token"})
