"""Shared HTTP-status → typed-error mapping for REST connectors.

Background
==========
``toolsconnector.errors`` ships a rich error taxonomy
(:class:`RateLimitError`, :class:`NotFoundError`, :class:`PermissionDeniedError`,
:class:`TokenExpiredError`, :class:`InvalidCredentialsError`,
:class:`ValidationError`, :class:`ConflictError`, :class:`ServerError`,
:class:`APIError`) so callers — especially AI agents — can branch on
**what kind** of failure occurred rather than parsing status codes from
``httpx.HTTPStatusError`` themselves.

Some connectors (Slack, LinkedIn, Discord, X, …) already map vendor
errors to typed exceptions inside their own ``_request`` method,
sometimes with vendor-specific body parsing
(Slack's ``{"ok": false, "error": "..."}``, LinkedIn's
``EXPIRED_ACCESS_TOKEN`` markers, etc.). Those connectors keep their
custom logic — this helper does not replace them.

Most connectors (Gmail, GitHub, OpenAI, Notion, Stripe, Jira, … —
~48 of them) historically just called ``response.raise_for_status()``
and let the bare ``httpx.HTTPStatusError`` bubble up. This helper
gives them a one-line drop-in replacement that buys typed errors with
no structural code change.

Usage
=====

Inside a connector's ``_request`` method, swap::

    response = await client.request(method, url, **kwargs)
    response.raise_for_status()

for::

    response = await client.request(method, url, **kwargs)
    raise_typed_for_status(response, connector=self.name)

That's the whole change. Successful responses (2xx, 3xx) are no-ops
just like ``raise_for_status``; failures raise the most specific class
the status code can identify.

Mapping
=======

==========  =========================================================
HTTP        Exception
==========  =========================================================
401         :class:`TokenExpiredError` if the response body contains
            ``"expired"``, ``"EXPIRED_ACCESS_TOKEN"``, or
            ``"REVOKED_ACCESS_TOKEN"``; otherwise
            :class:`InvalidCredentialsError`
403         :class:`PermissionDeniedError`
404         :class:`NotFoundError`
409         :class:`ConflictError`
400, 422    :class:`ValidationError`
429         :class:`RateLimitError` with ``retry_after_seconds`` parsed
            from the ``Retry-After`` header (numeric seconds; the
            HTTP-date form is not parsed — falls back to vendor default)
5xx         :class:`ServerError` (``retry_eligible=True``)
other 4xx   :class:`APIError`
==========  =========================================================

The raw response body (truncated to 500 chars) and full status code
are preserved on each exception's ``details`` dict for debugging.
"""

from __future__ import annotations

import re
from typing import Any, Optional

import httpx

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

# Maximum body bytes preserved on the exception's details dict. Larger
# bodies are truncated — preserves debuggability without bloating logs
# or exception repr() output.
_MAX_BODY_PREVIEW = 500

# Substrings in the 401 response body that strongly indicate the access
# token expired (vs. being malformed or revoked). Matched case-insensitively.
_TOKEN_EXPIRED_MARKERS = (
    "expired",
    "expired_access_token",
    "revoked_access_token",
    "token_expired",
)

# Regex patterns matching real credentials that some misbehaving upstreams
# echo back in error response bodies (request payload echoed for "debug",
# auth header reflected as "received: ..."). We redact these BEFORE
# storing the body preview on the exception so logs / observability
# pipelines never see the live secret.
#
# Patterns mirror the ones the CI's secret-leak grep enforces (see
# .github/workflows/ci.yml + .pre-commit-config.yaml). Keep them in sync.
_CREDENTIAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ghp_[A-Za-z0-9]{30,}"),  # GitHub PAT
    re.compile(r"xoxb-[0-9]{8,}-[0-9]{8,}-[A-Za-z0-9]{20,}"),  # Slack bot token
    re.compile(r"AKIA[A-Z0-9]{16}"),  # AWS access key
    re.compile(r"sk-ant-api03-[A-Za-z0-9_-]{80,}"),  # Anthropic key
    re.compile(r"sk_live_[A-Za-z0-9]{20,}"),  # Stripe live key
    # OpenAI keys: sk-..., sk-proj-..., sk-svcacct-... — needs dashes
    # in the body (sk-proj-... wouldn't match a [A-Za-z0-9]-only class).
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{20,}", re.IGNORECASE),  # Bearer tokens
)

_REDACTION_PLACEHOLDER = "[REDACTED]"


def raise_typed_for_status(
    response: httpx.Response,
    *,
    connector: str,
    action: Optional[str] = None,
) -> None:
    """Raise a typed error matching ``response.status_code``.

    Drop-in replacement for ``response.raise_for_status()`` — same
    no-op behavior on success, but failures bubble up as one of the
    classes from :mod:`toolsconnector.errors` instead of bare
    :class:`httpx.HTTPStatusError`.

    Args:
        response: The httpx response to inspect. Must be already-fetched
            (the body is read for the error's ``details`` field).
        connector: The name of the calling connector (e.g. ``"gmail"``,
            ``"github"``). Set on every typed error so downstream agents
            know which integration failed.
        action: Optional name of the action that issued the request
            (e.g. ``"send_email"``). Surfaced on the typed error for
            observability.

    Raises:
        TokenExpiredError: 401 with ``"expired"`` / token-revoked marker
            in the body.
        InvalidCredentialsError: 401 without an expired-token marker.
        PermissionDeniedError: 403.
        NotFoundError: 404.
        ConflictError: 409.
        ValidationError: 400 or 422.
        RateLimitError: 429.
        ServerError: 5xx.
        APIError: any other 4xx.
    """
    status = response.status_code
    if status < 400:
        # Success or redirect — same contract as raise_for_status().
        return

    body_preview = _safe_body_preview(response)
    details: dict[str, Any] = {
        "status_code": status,
        "body_preview": body_preview,
    }
    # `dict[str, Any]` annotation is required: mypy otherwise infers
    # the most-specific union of the literal values (str | int | dict |
    # None), which then fails to match the typed-error constructors'
    # individual kwarg signatures when we spread with `**base_kwargs`.
    # Each typed exception class validates its own params; this dict is
    # just a transport, so Any is appropriate here.
    base_kwargs: dict[str, Any] = {
        "connector": connector,
        "action": action,
        "details": details,
        "upstream_status": status,
    }
    message = f"{connector} API returned HTTP {status}"

    if status == 401:
        if _looks_like_expired_token(body_preview):
            raise TokenExpiredError(
                f"{message} (token appears expired)",
                **base_kwargs,
            )
        raise InvalidCredentialsError(message, **base_kwargs)

    if status == 403:
        raise PermissionDeniedError(message, **base_kwargs)

    if status == 404:
        raise NotFoundError(message, **base_kwargs)

    if status == 409:
        raise ConflictError(message, **base_kwargs)

    if status in (400, 422):
        raise ValidationError(message, **base_kwargs)

    if status == 429:
        retry_after = _parse_retry_after(response.headers.get("Retry-After"))
        # Only pass retry_after_seconds when we actually parsed a value —
        # passing None would explicitly override the class default of 60.0
        # rather than letting it apply.
        rl_kwargs: dict[str, Any] = {
            "connector": connector,
            "action": action,
            "details": details,
            "upstream_status": status,
        }
        if retry_after is not None:
            rl_kwargs["retry_after_seconds"] = retry_after
        raise RateLimitError(message, **rl_kwargs)

    if status >= 500:
        # 5xx and any non-standard codes >= 600 (rare but they exist —
        # some CDNs synthesize 6xx for upstream errors). Always treat as
        # server-side: caller retry is appropriate via ServerError's
        # ``retry_eligible=True`` default.
        raise ServerError(message, **base_kwargs)

    # Other 4xx (402, 405, 408, 410, 411, 413-418, 421, 423-431, 451 …):
    # known-error-class but not specifically modeled. Keep as APIError
    # so callers that do `except APIError` still catch it.
    raise APIError(message, **base_kwargs)


# --- internal helpers --------------------------------------------------------


def _safe_body_preview(response: httpx.Response) -> str:
    """Best-effort body extraction for the error's details field.

    Three guarantees:

    1. **Never raises.** If the body can't be decoded as text (e.g. binary
       response, malformed encoding), returns an empty string. Exception
       construction must not fail because of an oddly-encoded body.
    2. **Truncates to ``_MAX_BODY_PREVIEW`` chars** to keep exception
       repr / log output bounded.
    3. **Redacts known credential patterns** before returning. Some
       misbehaving upstreams echo the request's auth token (or other
       secrets posted in the body) back in the error response. Without
       redaction those would land in ``details["body_preview"]`` and
       leak into any sink that logs the exception. Patterns matched
       are the same ones the CI secret-scan grep enforces.
    """
    try:
        text = response.text
    except Exception:
        return ""
    if len(text) > _MAX_BODY_PREVIEW:
        text = text[:_MAX_BODY_PREVIEW] + "...[truncated]"
    return _redact_credentials(text)


def _redact_credentials(text: str) -> str:
    """Replace any credential-looking substrings with ``[REDACTED]``.

    Defensive — applied to every body preview regardless of whether
    we have evidence the upstream actually echoed a secret. The cost
    is one regex pass over up to ~500 bytes per error; the benefit
    is that no integrator's logs contain a live token because of us.
    """
    if not text:
        return text
    for pattern in _CREDENTIAL_PATTERNS:
        text = pattern.sub(_REDACTION_PLACEHOLDER, text)
    return text


def _looks_like_expired_token(body_preview: str) -> bool:
    """Heuristic — does the response body suggest the token expired?

    Checks for any of ``_TOKEN_EXPIRED_MARKERS`` (case-insensitive).
    Conservative: only matches on substrings that vendors actually use
    for expired-token signals (``EXPIRED_ACCESS_TOKEN``, ``token_expired``,
    plain ``expired``). False negatives just fall through to
    :class:`InvalidCredentialsError` which is still a correct (less
    specific) classification.
    """
    if not body_preview:
        return False
    haystack = body_preview.lower()
    return any(marker in haystack for marker in _TOKEN_EXPIRED_MARKERS)


def _parse_retry_after(header_value: Optional[str]) -> Optional[float]:
    """Parse a ``Retry-After`` header value into seconds.

    Per RFC 7231, the header can be either:
      - A delta-seconds integer (``Retry-After: 30``)
      - An HTTP-date (``Retry-After: Wed, 21 Oct 2025 07:28:00 GMT``)

    We parse only the integer form — the HTTP-date variant is rare in
    JSON APIs and would add ``email.utils.parsedate_to_datetime`` overhead
    on every error path. Date-form headers fall through to ``None``,
    which makes RateLimitError use its default of 60.0 s.

    Returns:
        Seconds as a float, never negative, or ``None`` if the header
        is missing or not a numeric value. Negative values are clamped
        to ``0.0`` so a hostile or buggy upstream can't trick the
        caller into ``await asyncio.sleep(-N)`` (which raises
        ``ValueError`` in stdlib asyncio and behaves inconsistently
        across third-party schedulers).
    """
    if not header_value:
        return None
    stripped = header_value.strip()
    try:
        seconds = float(stripped)
    except ValueError:
        return None
    return max(0.0, seconds)
