"""Unit tests for the shared ``raise_typed_for_status`` helper.

This is the framework piece used by ~48 connectors (Bucket B in the
plan-file inventory). Behavioral guarantees this file pins down:

  - 2xx / 3xx are no-ops (same contract as ``response.raise_for_status``)
  - Each 4xx/5xx status maps to the correct typed exception class
  - 401 with an "expired-token" body marker promotes to
    ``TokenExpiredError`` (vs. ``InvalidCredentialsError`` for plain bad creds)
  - 429 ``Retry-After: <seconds>`` is parsed onto ``retry_after_seconds``;
    HTTP-date form falls back to the class default
  - Body preview is truncated to keep exception details bounded
  - ``connector`` / ``action`` / ``upstream_status`` / ``details`` are
    populated on every raised exception so downstream agent code can
    branch on them
"""

from __future__ import annotations

import httpx
import pytest

from toolsconnector.connectors._helpers import raise_typed_for_status
from toolsconnector.errors import (
    APIError,
    ConflictError,
    InvalidCredentialsError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    TokenExpiredError,
    ValidationError,
)


def _resp(status: int, *, body: str = "", headers: dict | None = None) -> httpx.Response:
    """Build an ``httpx.Response`` shaped like a real upstream response.

    We attach a synthetic request because some httpx APIs unhappily complain
    about a response without one; tests only care about status + body + headers.
    """
    return httpx.Response(
        status,
        content=body.encode("utf-8"),
        headers=headers or {},
        request=httpx.Request("GET", "https://example.test/"),
    )


# ---------------------------------------------------------------------------
# Success path: 2xx / 3xx are no-ops
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [200, 201, 202, 204, 299, 301, 302, 304, 399])
def test_success_and_redirect_are_noop(status: int) -> None:
    """Same contract as ``response.raise_for_status()`` — anything below 400
    must NOT raise. Drop-in replacement guarantee.
    """
    raise_typed_for_status(_resp(status), connector="testconn")


# ---------------------------------------------------------------------------
# Status → exception class mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "exc_cls"),
    [
        (403, PermissionDeniedError),
        (404, NotFoundError),
        (409, ConflictError),
        (400, ValidationError),
        (422, ValidationError),
        (500, ServerError),
        (502, ServerError),
        (503, ServerError),
        (504, ServerError),
        # Other 4xx falls through to APIError
        (402, APIError),
        (405, APIError),
        (410, APIError),
        (418, APIError),
        (451, APIError),
    ],
)
def test_status_maps_to_typed_exception(status: int, exc_cls: type) -> None:
    """Each status code should raise its specific class — not a parent."""
    with pytest.raises(exc_cls) as exc_info:
        raise_typed_for_status(_resp(status, body=f"err {status}"), connector="gmail")

    err = exc_info.value
    # Connector + status survive the journey
    assert err.connector == "gmail"
    assert err.upstream_status == status
    assert err.details["status_code"] == status
    assert f"err {status}" in err.details["body_preview"]


def test_action_kwarg_propagates() -> None:
    """When the caller knows the action name, surface it on the error
    so observability layers can attribute the failure correctly.
    """
    with pytest.raises(NotFoundError) as exc_info:
        raise_typed_for_status(_resp(404, body=""), connector="github", action="get_repo")
    assert exc_info.value.action == "get_repo"


# ---------------------------------------------------------------------------
# 401 — expired-token vs. invalid-credentials disambiguation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        '{"error": "EXPIRED_ACCESS_TOKEN"}',
        '{"errorCode": "REVOKED_ACCESS_TOKEN"}',
        '{"error_description": "Access token has expired."}',
        '{"message": "token_expired"}',
        # Case-insensitive matching
        "ACCESS TOKEN EXPIRED",
    ],
)
def test_401_with_expired_marker_raises_token_expired(body: str) -> None:
    """401 + body marker → ``TokenExpiredError`` (more actionable for
    agents than the generic ``InvalidCredentialsError``: signals that
    a token refresh, not a re-auth, is the right next step).
    """
    with pytest.raises(TokenExpiredError):
        raise_typed_for_status(_resp(401, body=body), connector="linkedin")


@pytest.mark.parametrize(
    "body",
    [
        '{"error": "invalid_credentials"}',
        '{"message": "Bad token"}',
        # Empty body — can't disambiguate, defaults to InvalidCredentialsError
        "",
    ],
)
def test_401_without_expired_marker_raises_invalid_credentials(body: str) -> None:
    """401 without a token-expiry marker → ``InvalidCredentialsError``.

    Subclass relationship matters here — ``TokenExpiredError`` is also
    an ``AuthError``, so we explicitly assert the OUTER class isn't
    ``TokenExpiredError`` to catch a regression where the marker check
    becomes too loose.
    """
    with pytest.raises(InvalidCredentialsError) as exc_info:
        raise_typed_for_status(_resp(401, body=body), connector="github")
    assert not isinstance(exc_info.value, TokenExpiredError)


# ---------------------------------------------------------------------------
# 429 — Retry-After header parsing
# ---------------------------------------------------------------------------


def test_429_parses_retry_after_seconds() -> None:
    """``Retry-After: 30`` → ``retry_after_seconds = 30.0`` so callers can
    schedule a backoff that respects the upstream's hint.
    """
    with pytest.raises(RateLimitError) as exc_info:
        raise_typed_for_status(
            _resp(429, headers={"Retry-After": "30"}),
            connector="openai",
        )
    assert exc_info.value.retry_after_seconds == 30.0


def test_429_without_retry_after_uses_default() -> None:
    """Missing ``Retry-After`` shouldn't blow up; the class default
    (60.0) takes effect so the caller still has SOMETHING to back off by.
    """
    with pytest.raises(RateLimitError) as exc_info:
        raise_typed_for_status(_resp(429), connector="openai")
    # Class default is 60.0 — see RateLimitError.__init__ in errors/api.py
    assert exc_info.value.retry_after_seconds == 60.0


def test_429_http_date_format_falls_back_to_default() -> None:
    """RFC 7231 also allows ``Retry-After`` as an HTTP-date. We don't
    parse that form (rare in JSON APIs; would add date-parsing overhead
    on every error path). It silently falls through to the class
    default rather than raising — same UX as a missing header.
    """
    with pytest.raises(RateLimitError) as exc_info:
        raise_typed_for_status(
            _resp(429, headers={"Retry-After": "Wed, 21 Oct 2025 07:28:00 GMT"}),
            connector="github",
        )
    assert exc_info.value.retry_after_seconds == 60.0


# ---------------------------------------------------------------------------
# Body preview truncation
# ---------------------------------------------------------------------------


def test_body_preview_truncates_long_bodies() -> None:
    """Avoid bloating the exception's ``details`` dict (and any logs that
    repr it) with megabyte-sized error pages.
    """
    huge = "X" * 10_000
    with pytest.raises(NotFoundError) as exc_info:
        raise_typed_for_status(_resp(404, body=huge), connector="github")
    preview = exc_info.value.details["body_preview"]
    # Plan-file constant: _MAX_BODY_PREVIEW = 500
    assert len(preview) <= 600  # 500 + "...[truncated]" suffix
    assert preview.endswith("...[truncated]")


def test_undecodable_body_does_not_break_helper() -> None:
    """If the response body can't be decoded as text (e.g. raw bytes
    that aren't valid UTF-8), helper must not raise during exception
    construction — the original error class still surfaces correctly.
    """
    # Construct a response with deliberately invalid UTF-8
    binary = b"\xff\xfe\x80\x81 binary garbage"
    response = httpx.Response(
        500,
        content=binary,
        request=httpx.Request("GET", "https://example.test/"),
    )
    # Must raise ServerError, not crash on body decode
    with pytest.raises(ServerError):
        raise_typed_for_status(response, connector="testconn")
