"""OAuth 2.0 authorization-code flow -- token *acquisition* (BYOK-safe).

The existing :class:`~toolsconnector.runtime.auth.oauth2.OAuth2Provider` assumes
the caller already holds tokens; this module supplies the missing first step:
obtaining them. It is the "protocol exchange" only -- no hosted callback, no
token storage.

* :func:`begin` (pure, no network) builds the authorization URL and returns a
  :class:`PendingAuth` the caller must stash (a web app serializes it into the
  user's session; a desktop/CLI loopback helper holds it in memory).
* :func:`complete` (async) validates ``state`` and exchanges the code for a
  :class:`~toolsconnector.types.credentials.CredentialSet`, which then flows into
  ``OAuth2Provider`` / ``KeyStore`` unchanged.

PKCE (S256) is always used. Confidential clients also pass a ``client_secret``;
public clients (desktop/CLI) pass none -- PKCE is the proof instead.

See ``.agent/artifacts/oauth-flow-tier-a-plan.md``.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from pydantic import BaseModel

from toolsconnector.errors import AuthError
from toolsconnector.spec.auth import AuthType
from toolsconnector.types.credentials import CredentialSet


class OAuthFlowError(AuthError):
    """Raised when the authorization-code flow fails (state mismatch, token error)."""


@dataclass(frozen=True)
class ProviderPreset:
    """Endpoints + default authorization params for one OAuth provider.

    Presets are *data*: updating a provider means editing values here, not
    logic. Endpoints can also be overridden by the caller.
    """

    name: str
    auth_url: str
    token_url: str
    extra_auth_params: dict[str, str] = field(default_factory=dict)


# Google. access_type=offline + prompt=consent are REQUIRED to receive a refresh
# token -- without them Google returns an access token only. See the Tier A plan.
GOOGLE = ProviderPreset(
    name="google",
    auth_url="https://accounts.google.com/o/oauth2/v2/auth",
    token_url="https://oauth2.googleapis.com/token",
    extra_auth_params={"access_type": "offline", "prompt": "consent"},
)


class PendingAuth(BaseModel):
    """Flow state the caller must hold between :func:`begin` and :func:`complete`.

    Serialize into the user's session (web) or keep in memory (desktop/CLI).
    Carries the ``code_verifier`` (PKCE) and ``state`` (CSRF) so the exchange
    can prove itself.
    """

    authorization_url: str
    state: str
    code_verifier: str
    redirect_uri: str
    token_url: str
    client_id: str


def _pkce_pair() -> tuple[str, str]:
    """Return a ``(code_verifier, code_challenge)`` PKCE S256 pair."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def begin(
    preset: ProviderPreset,
    *,
    client_id: str,
    redirect_uri: str,
    scopes: list[str],
    state: Optional[str] = None,
    extra_params: Optional[dict[str, str]] = None,
) -> PendingAuth:
    """Build the authorization URL and PKCE/state material. No network.

    Args:
        preset: Provider endpoints + default params (e.g. :data:`GOOGLE`).
        client_id: OAuth client id.
        redirect_uri: Redirect registered with the provider (loopback for
            desktop, an app route for web).
        scopes: Scopes to request.
        state: Optional CSRF token; generated if omitted.
        extra_params: Extra authorization-URL params (override preset defaults).

    Returns:
        A :class:`PendingAuth` -- send the user to ``authorization_url`` and keep
        the object for :func:`complete`.
    """
    state = state or secrets.token_urlsafe(24)
    verifier, challenge = _pkce_pair()

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        **preset.extra_auth_params,
        **(extra_params or {}),
    }
    authorization_url = f"{preset.auth_url}?{urlencode(params)}"

    return PendingAuth(
        authorization_url=authorization_url,
        state=state,
        code_verifier=verifier,
        redirect_uri=redirect_uri,
        token_url=preset.token_url,
        client_id=client_id,
    )


def parse_redirect(url_or_query: str) -> dict[str, str]:
    """Parse the provider's redirect and raise on an error response.

    The web flow's counterpart to the loopback helper's denial handling: call
    this on the incoming callback URL (or its raw query string) before
    :func:`complete`, so a declined consent surfaces as the provider's actual
    reason instead of an opaque HTTP 400 from the token endpoint::

        params = parse_redirect(request.url)
        creds = await complete(pending, code=params["code"], state=params["state"])

    Args:
        url_or_query: The full redirect URL, or just its query string.

    Returns:
        The flattened query parameters (including ``code`` and ``state``).

    Raises:
        OAuthFlowError: If the provider returned ``error`` (e.g.
            ``access_denied``), or if no ``code`` is present.
    """
    query = urlparse(url_or_query).query or url_or_query
    params = {key: value[0] for key, value in parse_qs(query).items()}

    if "error" in params:
        detail = params.get("error_description") or params["error"]
        raise OAuthFlowError(f"Authorization was denied: {detail}")
    if not params.get("code"):
        raise OAuthFlowError(
            "Redirect carried neither an authorization code nor an error; "
            f"got parameters: {sorted(params)}",
        )
    return params


async def complete(
    pending: PendingAuth,
    *,
    code: str,
    state: str,
    client_secret: Optional[str] = None,
) -> CredentialSet:
    """Validate ``state`` and exchange the authorization ``code`` for tokens.

    Args:
        pending: The :class:`PendingAuth` from :func:`begin`.
        code: The ``code`` the provider sent to the redirect URI.
        state: The ``state`` the provider echoed back (compared against
            ``pending.state``).
        client_secret: Set for confidential clients; omit for public
            (PKCE-only) clients.

    Returns:
        A :class:`CredentialSet` (``auth_type=OAUTH2``) with the access token,
        refresh token (if issued) and absolute expiry -- ready for
        ``OAuth2Provider``.

    Raises:
        OAuthFlowError: On ``state`` mismatch, transport error, a non-200 token
            response, or a response without an ``access_token``.
    """
    if not isinstance(state, str) or not state:
        raise OAuthFlowError(
            "No OAuth state was returned to the redirect URI. Pass the provider's "
            "`state` query parameter through to complete(); a missing one cannot "
            "be checked against the value from begin().",
        )
    if not secrets.compare_digest(state, pending.state):
        raise OAuthFlowError("OAuth state mismatch -- possible CSRF; aborting token exchange.")
    if not isinstance(code, str) or not code:
        raise OAuthFlowError(
            "No authorization code was returned to the redirect URI. If the provider "
            "sent an `error` parameter instead, the user denied consent -- inspect it "
            "with parse_redirect() before calling complete().",
        )

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": pending.redirect_uri,
        "client_id": pending.client_id,
        "code_verifier": pending.code_verifier,
    }
    if client_secret:
        data["client_secret"] = client_secret

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                pending.token_url,
                data=data,
                headers={"Accept": "application/json"},
            )
    except httpx.HTTPError as exc:
        raise OAuthFlowError(f"HTTP error during token exchange: {exc}") from exc

    if response.status_code != 200:
        raise OAuthFlowError(
            f"Token endpoint returned HTTP {response.status_code}: {response.text}",
        )

    payload = response.json()
    access_token: Optional[str] = payload.get("access_token")
    if not access_token:
        raise OAuthFlowError("Token endpoint response did not contain an access_token.")

    token_expiry: Optional[datetime] = None
    expires_in = payload.get("expires_in")
    if expires_in is not None:
        token_expiry = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

    # The provider's `scope` is the ONLY authority on what the token actually
    # covers: Google's granular consent lets a user untick individual boxes, and
    # include_granted_scopes=true can return *more* than was requested. Carry it
    # through so callers can compare granted vs requested instead of assuming.
    extra: dict[str, Any] = {}
    granted_raw = payload.get("scope")
    if granted_raw:
        extra["granted_scopes"] = granted_raw.split()
    if payload.get("token_type"):
        extra["token_type"] = payload["token_type"]

    return CredentialSet(
        auth_type=AuthType.OAUTH2,
        access_token=access_token,
        refresh_token=payload.get("refresh_token"),
        token_expiry=token_expiry,
        client_id=pending.client_id,
        client_secret=client_secret,
        extra=extra,
    )


def granted_scopes(credentials: CredentialSet) -> Optional[list[str]]:
    """Return the scopes the provider actually granted, if it reported them.

    Args:
        credentials: A credential set produced by :func:`complete`.

    Returns:
        The granted scope list, or ``None`` when the provider did not report
        one (in which case the requested scopes are the best available guess).
    """
    value = credentials.extra.get("granted_scopes")
    return list(value) if value else None


def missing_scopes(credentials: CredentialSet, required: list[str]) -> list[str]:
    """Return the *required* scopes the provider did not grant.

    Use after :func:`complete` to detect a partial consent before the first API
    call fails::

        missing = missing_scopes(creds, oauth_scopes(Gmail))
        if missing:
            raise SystemExit(f"Not authorized for: {missing}")

    Args:
        credentials: A credential set produced by :func:`complete`.
        required: The scopes the caller needs.

    Returns:
        The missing scopes, or ``[]`` when nothing is missing **or** the
        provider reported no scope at all (nothing can be concluded).
    """
    granted = granted_scopes(credentials)
    if granted is None:
        return []
    return [scope for scope in required if scope not in granted]
