"""Self-refreshing OAuth credentials for connectors.

:class:`RefreshingCredentials` is a **callable** that returns a currently-valid
access token, exchanging the refresh token when the current one is near expiry.
Because connectors resolve a callable on every credential access (see
:attr:`~toolsconnector.runtime.base.BaseConnector._credentials`), passing one in
gives a long-lived connector automatic token renewal with no connector change::

    creds = asyncio.run(login_for(Gmail, client_id=..., client_secret=...))
    auth = RefreshingCredentials(creds, client_id=..., client_secret=...,
                                 on_refresh=save_somewhere)
    gmail = Gmail(credentials=auth)      # keeps working past the 1-hour expiry

TC still stores nothing: ``on_refresh`` hands rotated tokens back to the caller
to persist wherever they choose (their vault, a KeyStore, a file, nowhere).

.. note::
   :meth:`__call__` refreshes **synchronously** (the credential property that
   invokes it is sync), so inside an event loop it blocks for the duration of
   one token request, at most once per token lifetime (~1 hour). This mirrors
   ``google-auth``'s behaviour. To keep the loop free, call
   :meth:`arefresh` yourself ahead of time -- ``__call__`` will then find a
   valid token and never block.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

import httpx

from toolsconnector.errors import RefreshFailedError, TokenExpiredError
from toolsconnector.types.credentials import CredentialSet

from .flows import GOOGLE, ProviderPreset

logger = logging.getLogger("toolsconnector")

# Refresh this many seconds before the token actually expires.
_DEFAULT_BUFFER_SECONDS = 60


class RefreshingCredentials:
    """A callable credential that renews its access token on demand.

    Args:
        credentials: The :class:`CredentialSet` from the OAuth flow. Must
            carry a ``refresh_token`` for renewal to be possible.
        client_id: OAuth client id. Defaults to ``credentials.client_id``.
        client_secret: OAuth client secret (omit for public/PKCE clients).
            Defaults to ``credentials.client_secret``.
        preset: Provider preset supplying the token endpoint. Defaults to
            :data:`~toolsconnector.runtime.auth.flows.GOOGLE`.
        on_refresh: Called with the updated :class:`CredentialSet` after every
            successful refresh, so the caller can persist rotated tokens.
        buffer_seconds: Refresh this many seconds before actual expiry.

    Raises:
        ValueError: If *credentials* has no ``access_token``.
    """

    def __init__(
        self,
        credentials: CredentialSet,
        *,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        preset: ProviderPreset = GOOGLE,
        on_refresh: Optional[Callable[[CredentialSet], Any]] = None,
        buffer_seconds: int = _DEFAULT_BUFFER_SECONDS,
    ) -> None:
        if not credentials.access_token:
            raise ValueError("RefreshingCredentials requires an access_token.")
        self._credentials = credentials
        self._client_id = client_id or credentials.client_id
        self._client_secret = client_secret or credentials.client_secret
        self._preset = preset
        self._on_refresh = on_refresh
        self._buffer = buffer_seconds
        self._lock = threading.Lock()
        self._refreshed_once = False

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------

    @property
    def credentials(self) -> CredentialSet:
        """The current credential set (including any rotated refresh token)."""
        return self._credentials

    def needs_refresh(self) -> bool:
        """Whether the access token is expired or within the refresh buffer.

        An **unknown** expiry (``token_expiry is None``) counts as needing a
        refresh, once. A credential rehydrated from a caller's vault often drops
        the timestamp, and treating that as "never expires" silently degrades
        this object into a static token that dies at the provider's real expiry
        with a misleading error. Refreshing once establishes a real expiry; if
        there is no refresh token to do it with, :meth:`__call__` uses the
        access token as-is rather than failing a credential that may be valid.

        Returns:
            ``True`` if a refresh should be attempted before the next request.
        """
        expiry = self._credentials.token_expiry
        if expiry is None:
            return not self._refreshed_once
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        return (expiry - datetime.now(timezone.utc)).total_seconds() <= self._buffer

    def __call__(self) -> str:
        """Return a valid access token, refreshing first if needed.

        Raises:
            TokenExpiredError: If the token expired and no refresh token exists.
            RefreshFailedError: If the token endpoint rejects the refresh.
        """
        if self.needs_refresh():
            with self._lock:
                # Re-check: another thread may have refreshed while we waited.
                if self.needs_refresh():
                    expiry_unknown = self._credentials.token_expiry is None
                    if expiry_unknown and not self._credentials.refresh_token:
                        # Nothing to refresh with, and no evidence the token is
                        # dead. Use it; a real expiry surfaces as a 401.
                        self._refreshed_once = True
                    elif expiry_unknown:
                        # Opportunistic: establish a real expiry if we can, but
                        # never turn an *unproven* expiry into a hard failure --
                        # the current token may be perfectly valid.
                        try:
                            self._refresh_sync()
                        except (RefreshFailedError, TokenExpiredError) as exc:
                            self._refreshed_once = True
                            logger.warning(
                                "Could not refresh a credential with unknown expiry (%s); "
                                "using the existing access token. It will fail with a 401 "
                                "if it has already expired.",
                                exc,
                            )
                    else:
                        # Expiry is known and has passed: the token IS dead, so a
                        # failed refresh must surface.
                        self._refresh_sync()
        token = self._credentials.access_token
        if token is None:  # pragma: no cover - guarded in __init__/refresh
            raise TokenExpiredError("No access token available.")
        return token

    async def arefresh(self) -> CredentialSet:
        """Refresh without blocking the event loop.

        Returns:
            The updated :class:`CredentialSet`.
        """
        payload = self._refresh_payload()
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self._preset.token_url,
                    data=payload,
                    headers={"Accept": "application/json"},
                )
        except httpx.HTTPError as exc:
            raise RefreshFailedError(f"HTTP error during token refresh: {exc}") from exc
        return self._apply(response)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _refresh_payload(self) -> dict[str, str]:
        refresh_token = self._credentials.refresh_token
        if not refresh_token:
            raise TokenExpiredError(
                "Access token expired and no refresh token is available -- "
                "re-run the OAuth flow (login_for/complete) to get a new one.",
            )
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self._client_id or "",
        }
        if self._client_secret:
            payload["client_secret"] = self._client_secret
        return payload

    def _refresh_sync(self) -> CredentialSet:
        payload = self._refresh_payload()
        try:
            with httpx.Client() as client:
                response = client.post(
                    self._preset.token_url,
                    data=payload,
                    headers={"Accept": "application/json"},
                )
        except httpx.HTTPError as exc:
            raise RefreshFailedError(f"HTTP error during token refresh: {exc}") from exc
        return self._apply(response)

    def _apply(self, response: httpx.Response) -> CredentialSet:
        """Validate a token response and fold it into the credential set."""
        if response.status_code != 200:
            raise RefreshFailedError(
                f"Token endpoint returned HTTP {response.status_code}: {response.text}",
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise RefreshFailedError(
                f"Token endpoint returned non-JSON response: {response.text[:200]}",
            ) from exc

        access_token = data.get("access_token")
        if not access_token:
            raise RefreshFailedError("Token refresh response did not contain an access_token.")

        expires_in = data.get("expires_in")
        token_expiry = None
        if expires_in is not None:
            token_expiry = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

        extra = dict(self._credentials.extra)
        # The refresh response restates the granted scopes; they can shrink if the
        # user revoked part of the grant since acquisition.
        if data.get("scope"):
            extra["granted_scopes"] = data["scope"].split()

        self._credentials = self._credentials.model_copy(
            update={
                "access_token": access_token,
                # Providers may rotate the refresh token; keep the old one if not.
                "refresh_token": data.get("refresh_token") or self._credentials.refresh_token,
                "token_expiry": token_expiry,
                "extra": extra,
            }
        )
        self._refreshed_once = True
        if self._on_refresh is not None:
            self._on_refresh(self._credentials)
        return self._credentials
