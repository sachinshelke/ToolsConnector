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
        # Non-standard 6xx codes that some CDNs synthesize for upstream
        # failures — should still be ServerError (retry-eligible) rather
        # than the generic APIError fallthrough.
        (600, ServerError),
        (699, ServerError),
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


def test_429_negative_retry_after_clamped_to_zero() -> None:
    """A hostile or buggy upstream sending ``Retry-After: -30`` must NOT
    cause ``await asyncio.sleep(-30)`` in the caller (raises ValueError
    in stdlib asyncio). Helper clamps negative seconds to 0.0 — the
    caller still gets a typed RateLimitError but with a safe sleep value.
    """
    with pytest.raises(RateLimitError) as exc_info:
        raise_typed_for_status(
            _resp(429, headers={"Retry-After": "-30"}),
            connector="testconn",
        )
    assert exc_info.value.retry_after_seconds == 0.0


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
# 429 — Google Workspace edge cases
# ---------------------------------------------------------------------------
#
# Google APIs (Drive/Sheets/Docs/Calendar/Tasks) have a per-user AND a
# per-project quota. When either is exhausted, the 429 body distinguishes
# the cause via ``error.errors[*].reason``. The shared helper preserves
# the structured body in ``details["body_preview"]`` so callers (or AI
# agents) can branch — these tests pin that contract.


def test_429_google_user_rate_limit_exceeded_preserves_reason_in_body() -> None:
    """Google's per-user 429 — body carries ``reason: userRateLimitExceeded``.

    The shared helper does not parse the structured body (that would be
    vendor-specific). It DOES copy the body into ``details["body_preview"]``
    so a caller catching ``RateLimitError`` can inspect it and distinguish
    per-user from per-project throttling.
    """
    body = (
        '{"error":{"code":429,"message":"User Rate Limit Exceeded",'
        '"errors":[{"reason":"userRateLimitExceeded","domain":"usageLimits"}]}}'
    )
    with pytest.raises(RateLimitError) as exc_info:
        raise_typed_for_status(
            _resp(429, body=body, headers={"Retry-After": "30"}),
            connector="gdrive",
        )
    assert exc_info.value.retry_after_seconds == 30.0
    assert "userRateLimitExceeded" in exc_info.value.details["body_preview"]


def test_429_google_quota_exceeded_preserves_reason_in_body() -> None:
    """Google's per-project quota 429 — body carries ``reason: quotaExceeded``.

    Distinct from ``userRateLimitExceeded`` — recovery here means
    contacting the Cloud Console project owner / raising a quota
    increase, not just backing off. We pin that the body distinguishes
    these so caller code can branch.
    """
    body = (
        '{"error":{"code":429,"message":"Quota exceeded for the project",'
        '"errors":[{"reason":"quotaExceeded","domain":"usageLimits"}]}}'
    )
    with pytest.raises(RateLimitError) as exc_info:
        raise_typed_for_status(_resp(429, body=body), connector="gcalendar")
    assert "quotaExceeded" in exc_info.value.details["body_preview"]
    # No Retry-After header → defaults to 60s
    assert exc_info.value.retry_after_seconds == 60.0


def test_429_retry_after_whitespace_padded() -> None:
    """Some proxies pad header values (`Retry-After:  30  `). The parser
    strips before float-conversion so padding doesn't fall through to
    the default.
    """
    with pytest.raises(RateLimitError) as exc_info:
        raise_typed_for_status(
            _resp(429, headers={"Retry-After": "  30  "}),
            connector="gdrive",
        )
    assert exc_info.value.retry_after_seconds == 30.0


def test_429_retry_after_fractional_seconds() -> None:
    """Some upstreams emit fractional seconds (`Retry-After: 1.5`). Spec
    permits delta-seconds as ``1*DIGIT`` (integer-only), but the parser
    accepts float so we don't double-down on a hostile-upstream interop
    bug and end up with the 60s default.
    """
    with pytest.raises(RateLimitError) as exc_info:
        raise_typed_for_status(
            _resp(429, headers={"Retry-After": "1.5"}),
            connector="gsheets",
        )
    assert exc_info.value.retry_after_seconds == 1.5


def test_429_retry_after_zero_means_retry_immediately() -> None:
    """``Retry-After: 0`` is a valid signal meaning "retry now". The
    parser must round-trip it as 0.0, not coerce to the default 60s.
    Otherwise a caller that respects the hint sleeps an unwarranted
    minute on every soft-throttle.
    """
    with pytest.raises(RateLimitError) as exc_info:
        raise_typed_for_status(
            _resp(429, headers={"Retry-After": "0"}),
            connector="gdrive",
        )
    assert exc_info.value.retry_after_seconds == 0.0


def test_429_retry_after_garbage_value_uses_default() -> None:
    """A non-numeric, non-HTTP-date value (`Retry-After: soon`) cannot
    be honored. The parser returns None, the class default (60s) kicks
    in — no exception leaks out of the parser itself.
    """
    with pytest.raises(RateLimitError) as exc_info:
        raise_typed_for_status(
            _resp(429, headers={"Retry-After": "soon"}),
            connector="gdrive",
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


# Synthetic credential-shaped strings — match the helper's regex
# patterns but obviously fake (no real-world secret here). The
# `# fake test credential` comment on each line is what the
# pre-commit secret-leak hook looks for to skip the line — keep it.
_FAKE_GH_PAT = "ghp_" + "0" * 30 + "FAKETESTPAT1234"  # fake test credential — classic PAT
_FAKE_GH_FINE = "github_pat_" + "D" * 70  # fake test credential — fine-grained PAT
_FAKE_GH_OAUTH = "gho_" + "E" * 35  # fake test credential — OAuth access token
_FAKE_GH_APP_INSTALL = "ghs_" + "F" * 35  # fake test credential — App installation token
_FAKE_GH_APP_USER = "ghu_" + "G" * 35  # fake test credential — App user access token
_FAKE_GH_REFRESH = "ghr_" + "H" * 35  # fake test credential — App refresh token
_FAKE_ANTHROPIC = "sk-ant-api03-" + "a" * 90  # fake test credential
_FAKE_STRIPE = "sk_live_" + "Z" * 30  # fake test credential (placeholder)
_FAKE_OPENAI = "sk-proj-" + "Q" * 30  # fake test credential (placeholder)
_FAKE_SLACK = "xoxb-12345678-87654321-" + "Y" * 24  # fake test credential
_FAKE_AWS = "AKIAIOSFODNN7EXAMPLE"  # fake test credential — AWS docs example
_FAKE_BEARER = "Bearer ya29.a0AfH6SMB" + "x" * 24  # fake test credential
_FAKE_NOTION_LEGACY = "secret_" + "A" * 43  # fake test credential — Notion legacy token shape
_FAKE_NOTION_NTN = "ntn_" + "B" * 46  # fake test credential — Notion ntn_ token shape
_FAKE_LINEAR = "lin_api_" + "C" * 32  # fake test credential — Linear personal API key shape
_FAKE_GOOGLE_OAUTH = (
    "ya29." + "I" * 80
)  # fake test credential — Google OAuth 2.0 access token shape
_FAKE_GOOGLE_APIKEY = "AIza" + "J" * 35  # fake test credential — Google API key shape


@pytest.mark.parametrize(
    ("secret_in_body", "description"),
    [
        (_FAKE_GH_PAT, "GitHub PAT (classic ghp_*)"),
        (_FAKE_GH_FINE, "GitHub fine-grained PAT (github_pat_*)"),
        (_FAKE_GH_OAUTH, "GitHub OAuth access token (gho_*)"),
        (_FAKE_GH_APP_INSTALL, "GitHub App installation token (ghs_*)"),
        (_FAKE_GH_APP_USER, "GitHub App user access token (ghu_*)"),
        (_FAKE_GH_REFRESH, "GitHub App refresh token (ghr_*)"),
        (_FAKE_ANTHROPIC, "Anthropic API key"),
        (_FAKE_STRIPE, "Stripe live key"),
        (_FAKE_OPENAI, "OpenAI key"),
        (_FAKE_SLACK, "Slack bot token"),
        (_FAKE_AWS, "AWS access key"),
        (_FAKE_BEARER, "OAuth bearer (Google-style)"),
        (_FAKE_NOTION_LEGACY, "Notion integration token (legacy secret_*)"),
        (_FAKE_NOTION_NTN, "Notion integration token (current ntn_*)"),
        (_FAKE_LINEAR, "Linear personal API key (lin_api_*)"),
        (_FAKE_GOOGLE_OAUTH, "Google OAuth 2.0 access token (ya29.*)"),
        (_FAKE_GOOGLE_APIKEY, "Google API key (AIza*)"),
    ],
)
def test_body_preview_redacts_echoed_credentials(secret_in_body: str, description: str) -> None:
    """Some misbehaving upstreams echo the request's auth token (or
    other secrets posted in the body) back in the error response.
    Without redaction those would land in ``details["body_preview"]``
    and leak into any sink that logs the exception.

    Helper redacts known credential patterns inline before storing.
    """
    body = f'{{"error":"invalid_token","received":"{secret_in_body}"}}'
    with pytest.raises(InvalidCredentialsError) as exc_info:
        raise_typed_for_status(_resp(401, body=body), connector="testconn")

    preview = exc_info.value.details["body_preview"]
    assert secret_in_body not in preview, f"{description} leaked into body_preview unredacted"
    assert "[REDACTED]" in preview


def test_body_preview_does_not_redact_innocuous_strings() -> None:
    """Make sure the redaction patterns are tight enough to not
    munge ordinary error messages. False positives would degrade
    debuggability with no security benefit.
    """
    innocuous = "Resource not found. ID: usr_12345abc. Try GET /users instead."
    with pytest.raises(NotFoundError) as exc_info:
        raise_typed_for_status(_resp(404, body=innocuous), connector="testconn")
    assert exc_info.value.details["body_preview"] == innocuous


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
