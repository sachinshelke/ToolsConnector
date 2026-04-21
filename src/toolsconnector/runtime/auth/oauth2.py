"""OAuth 2.0 authentication provider.

Manages the access-token lifecycle: injects the bearer token into
requests, checks expiry with a configurable buffer, and exchanges
refresh tokens for new access tokens via the provider's token
endpoint using ``httpx``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from toolsconnector.errors import (
    InvalidCredentialsError,
    RefreshFailedError,
    TokenExpiredError,
)
from toolsconnector.keystore.base import KeyStore
from toolsconnector.spec.auth import AuthType
from toolsconnector.types.credentials import CredentialSet, OAuthConfig

from .base import AuthState

# Default number of seconds before actual expiry to trigger a refresh.
_REFRESH_BUFFER_SECONDS: int = 60


class OAuth2Provider:
    """Auth provider for OAuth 2.0 bearer-token flows.

    The provider does **not** implement the authorization-code grant
    or redirect handling -- those are the caller's responsibility
    (BYOK model).  Instead it expects pre-obtained tokens in a
    :class:`~toolsconnector.types.credentials.CredentialSet` and
    manages the refresh cycle automatically.

    Args:
        oauth_config: Runtime OAuth configuration with token URL and
            client credentials.
        credentials: Pre-obtained credential set containing at least
            an ``access_token``.
        keystore: Credential storage backend for persisting refreshed
            tokens.
        connector_name: Connector identifier used as the keystore
            namespace.
        refresh_buffer_seconds: Number of seconds before token expiry
            to proactively refresh.  Defaults to ``60``.

    Raises:
        InvalidCredentialsError: If no *access_token* is provided in
            *credentials*.

    Example::

        provider = OAuth2Provider(
            oauth_config=OAuthConfig(
                auth_url="https://accounts.google.com/o/oauth2/v2/auth",
                token_url="https://oauth2.googleapis.com/token",
                client_id="...",
                client_secret="...",
            ),
            credentials=CredentialSet(
                auth_type=AuthType.OAUTH2,
                access_token="ya29.xxx",
                refresh_token="1//0xxx",
                token_expiry=datetime(2025, 1, 1, tzinfo=timezone.utc),
            ),
            keystore=my_keystore,
            connector_name="gmail",
        )
    """

    auth_type: str = AuthType.OAUTH2.value

    def __init__(
        self,
        oauth_config: OAuthConfig,
        credentials: CredentialSet,
        keystore: KeyStore,
        connector_name: str = "default",
        refresh_buffer_seconds: int = _REFRESH_BUFFER_SECONDS,
    ) -> None:
        if not credentials.access_token:
            raise InvalidCredentialsError(
                "OAuth2Provider requires an access_token in the credential set.",
            )

        self._oauth_config = oauth_config
        self._credentials = credentials
        self._keystore = keystore
        self._connector_name = connector_name
        self._refresh_buffer = refresh_buffer_seconds

        self._state = AuthState(
            access_token=credentials.access_token,
            refresh_token=credentials.refresh_token,
            token_expiry=credentials.token_expiry,
            scopes=oauth_config.scopes,
            is_authenticated=True,
        )

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @property
    def state(self) -> AuthState:
        """Return the current auth state (read-only snapshot).

        Returns:
            The current :class:`AuthState`.
        """
        return self._state.model_copy()

    # ------------------------------------------------------------------
    # AuthProvider protocol
    # ------------------------------------------------------------------

    async def authenticate(
        self,
        headers: dict[str, str],
        params: dict[str, str],
    ) -> None:
        """Inject the ``Authorization: Bearer`` header.

        If the token has expired and no refresh is possible, a
        :class:`~toolsconnector.errors.TokenExpiredError` is raised
        so the caller can re-authenticate from scratch.

        Args:
            headers: Mutable HTTP headers dict.
            params: Mutable query-parameter dict (unused).

        Raises:
            TokenExpiredError: If the token is expired and cannot be
                refreshed.
        """
        if self.needs_refresh() and not self._state.refresh_token:
            raise TokenExpiredError(
                "Access token has expired and no refresh token is available.",
            )
        headers["Authorization"] = f"Bearer {self._state.access_token}"

    async def refresh(self) -> None:
        """Exchange the refresh token for a new access token.

        Performs a ``POST`` to the token URL with
        ``grant_type=refresh_token``.  On success, updates
        :attr:`_state` and persists the new tokens to the keystore.

        Raises:
            RefreshFailedError: If the token endpoint returns an
                error or the HTTP request fails.
        """
        if not self._state.refresh_token:
            raise RefreshFailedError(
                "No refresh token available for token renewal.",
            )

        payload: dict[str, str] = {
            "grant_type": "refresh_token",
            "refresh_token": self._state.refresh_token,
            "client_id": self._oauth_config.client_id,
            "client_secret": self._oauth_config.client_secret,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self._oauth_config.token_url,
                    data=payload,
                    headers={"Accept": "application/json"},
                )
        except httpx.HTTPError as exc:
            raise RefreshFailedError(
                f"HTTP error during token refresh: {exc}",
            ) from exc

        if response.status_code != 200:
            raise RefreshFailedError(
                f"Token endpoint returned HTTP {response.status_code}: {response.text}",
            )

        data = response.json()
        new_access_token: Optional[str] = data.get("access_token")
        if not new_access_token:
            raise RefreshFailedError(
                "Token endpoint response did not contain an access_token.",
            )

        expires_in: Optional[int] = data.get("expires_in")
        new_expiry: Optional[datetime] = None
        if expires_in is not None:
            new_expiry = datetime.now(timezone.utc) + timedelta(
                seconds=int(expires_in),
            )

        # Some providers rotate refresh tokens; honour the new one if present.
        new_refresh_token: Optional[str] = data.get(
            "refresh_token",
            self._state.refresh_token,
        )

        # Update internal state.
        self._state.access_token = new_access_token
        self._state.refresh_token = new_refresh_token
        self._state.token_expiry = new_expiry
        self._state.is_authenticated = True

        # Persist to keystore.
        await self._persist_tokens()

    def needs_refresh(self) -> bool:
        """Check whether the access token is expired or about to expire.

        Uses a configurable buffer (default 60 s) so that callers
        can refresh proactively.

        Returns:
            ``True`` if the token expiry is within the buffer window
            (or already past), ``False`` otherwise.  Also returns
            ``False`` if no expiry is set (tokens without an explicit
            TTL are assumed to be long-lived).
        """
        if self._state.token_expiry is None:
            return False
        now = datetime.now(timezone.utc)
        # Ensure expiry is offset-aware for comparison.
        expiry = self._state.token_expiry
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        delta = (expiry - now).total_seconds()
        return delta <= self._refresh_buffer

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _persist_tokens(self) -> None:
        """Write the current tokens to the keystore.

        Keys follow the naming convention
        ``{connector}:default:{field}``.
        """
        prefix = f"{self._connector_name}:default"

        if self._state.access_token:
            ttl: Optional[int] = None
            if self._state.token_expiry is not None:
                remaining = (self._state.token_expiry - datetime.now(timezone.utc)).total_seconds()
                if remaining > 0:
                    ttl = int(remaining)
            await self._keystore.set(
                f"{prefix}:access_token",
                self._state.access_token,
                ttl=ttl,
            )

        if self._state.refresh_token:
            await self._keystore.set(
                f"{prefix}:refresh_token",
                self._state.refresh_token,
            )
