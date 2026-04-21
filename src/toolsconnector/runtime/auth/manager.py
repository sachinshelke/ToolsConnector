"""Auth manager -- orchestrates provider selection and token lifecycle.

The :class:`AuthManager` acts as the single entry-point for the
runtime transport layer: given a :class:`CredentialSet` it selects
the matching :class:`AuthProvider`, handles token refresh with
concurrency-safe locking, and persists refreshed tokens to the
:class:`KeyStore`.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import Optional

from toolsconnector.errors import AuthError, RefreshFailedError
from toolsconnector.keystore.base import KeyStore
from toolsconnector.types.credentials import CredentialSet

from .base import AuthProvider

logger = logging.getLogger(__name__)


class AuthManager:
    """Manages auth-provider selection and token refresh.

    The manager is designed to sit between the connector runtime and
    the HTTP transport layer.  Before each request, the transport
    calls :meth:`get_auth_headers` to obtain up-to-date
    authentication headers (and optionally query params).

    Concurrency safety is guaranteed by an :class:`asyncio.Lock` that
    prevents multiple coroutines from refreshing the same token
    simultaneously.

    Args:
        providers: One or more :class:`AuthProvider` instances that
            the connector supports.
        keystore: Storage backend for persisting refreshed tokens.
        credentials: The active credential set that determines which
            provider is selected.

    Raises:
        AuthError: If no registered provider matches the credential
            set's :attr:`~CredentialSet.auth_type`.

    Example::

        manager = AuthManager(
            providers=[api_key_prov, oauth_prov],
            keystore=memory_store,
            credentials=cred_set,
        )
        headers = await manager.get_auth_headers()
    """

    def __init__(
        self,
        providers: Sequence[AuthProvider],
        keystore: KeyStore,
        credentials: CredentialSet,
    ) -> None:
        self._providers = {p.auth_type: p for p in providers}
        self._keystore = keystore
        self._credentials = credentials
        self._refresh_lock = asyncio.Lock()
        self._active_provider: Optional[AuthProvider] = self._resolve_provider()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def active_provider(self) -> AuthProvider:
        """Return the currently active auth provider.

        Returns:
            The :class:`AuthProvider` matching the credential set.

        Raises:
            AuthError: If no provider could be resolved.
        """
        if self._active_provider is None:
            raise AuthError(
                "No auth provider is active. "
                "Ensure a provider matching the credential set is registered.",
            )
        return self._active_provider

    async def get_auth_headers(self) -> dict[str, str]:
        """Return HTTP headers (and optionally params) for the next request.

        If the active provider's token needs refreshing, a refresh is
        attempted first (under a lock to avoid thundering-herd
        refreshes).

        Returns:
            A dict of HTTP headers that should be merged into the
            outgoing request.

        Raises:
            AuthError: If authentication or refresh fails.
        """
        provider = self.active_provider

        if provider.needs_refresh():
            await self._safe_refresh(provider)

        headers: dict[str, str] = {}
        params: dict[str, str] = {}
        await provider.authenticate(headers, params)
        return headers

    async def get_auth_params(self) -> dict[str, str]:
        """Return query parameters for the next request.

        Behaves identically to :meth:`get_auth_headers` but returns
        the query-parameter dict instead.

        Returns:
            A dict of query parameters to merge into the request URL.

        Raises:
            AuthError: If authentication or refresh fails.
        """
        provider = self.active_provider

        if provider.needs_refresh():
            await self._safe_refresh(provider)

        headers: dict[str, str] = {}
        params: dict[str, str] = {}
        await provider.authenticate(headers, params)
        return params

    async def get_full_auth(self) -> tuple[dict[str, str], dict[str, str]]:
        """Return both headers and params for the next request.

        Convenience method that avoids calling
        :meth:`authenticate` twice.

        Returns:
            A ``(headers, params)`` tuple.

        Raises:
            AuthError: If authentication or refresh fails.
        """
        provider = self.active_provider

        if provider.needs_refresh():
            await self._safe_refresh(provider)

        headers: dict[str, str] = {}
        params: dict[str, str] = {}
        await provider.authenticate(headers, params)
        return headers, params

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resolve_provider(self) -> Optional[AuthProvider]:
        """Select the provider that matches the credential set.

        Returns:
            The matching provider, or ``None`` if no match exists.
        """
        auth_type_value = self._credentials.auth_type.value
        provider = self._providers.get(auth_type_value)
        if provider is None:
            logger.warning(
                "No registered auth provider for auth_type=%r. Available: %s",
                auth_type_value,
                list(self._providers.keys()),
            )
        return provider

    async def _safe_refresh(self, provider: AuthProvider) -> None:
        """Refresh the provider's token under a concurrency lock.

        If another coroutine is already refreshing, this one waits
        for the lock and then re-checks whether a refresh is still
        needed (double-check locking).

        Args:
            provider: The provider to refresh.

        Raises:
            RefreshFailedError: If the refresh attempt fails.
        """
        async with self._refresh_lock:
            # Double-check after acquiring the lock -- another
            # coroutine may have refreshed while we were waiting.
            if not provider.needs_refresh():
                return

            logger.debug("Refreshing credentials for provider %s", provider.auth_type)
            try:
                await provider.refresh()
            except RefreshFailedError:
                raise
            except Exception as exc:
                raise RefreshFailedError(
                    f"Unexpected error during token refresh: {exc}",
                ) from exc
            logger.debug("Token refresh succeeded for provider %s", provider.auth_type)
