"""Base auth provider protocol and auth state model.

Defines the :class:`AuthProvider` protocol that all authentication
providers must satisfy, and the :class:`AuthState` Pydantic model for
tracking the current state of a credential lifecycle.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Protocol, runtime_checkable

from pydantic import BaseModel, Field


@runtime_checkable
class AuthProvider(Protocol):
    """Pluggable auth provider.

    Every concrete authentication strategy (API key, Bearer token,
    OAuth 2.0, Basic, etc.) implements this protocol so the
    :class:`~toolsconnector.runtime.auth.manager.AuthManager` can
    interact with them uniformly.

    Attributes:
        auth_type: Machine-readable auth type identifier that matches
            :class:`~toolsconnector.spec.auth.AuthType` values.
    """

    auth_type: str

    async def authenticate(
        self,
        headers: dict[str, str],
        params: dict[str, str],
    ) -> None:
        """Modify *headers* and/or *params* to add authentication.

        The caller passes mutable dicts; the provider mutates them
        in-place to inject credentials (e.g. an ``Authorization``
        header or a query-string API key).

        Args:
            headers: HTTP headers dict to mutate.
            params: URL query-parameter dict to mutate.
        """
        ...

    async def refresh(self) -> None:
        """Refresh credentials if the underlying scheme supports it.

        For static schemes (API key, Basic) this is a no-op.
        For OAuth 2.0 this exchanges a refresh token for a new
        access token.

        Raises:
            RefreshFailedError: If the refresh attempt fails.
        """
        ...

    def needs_refresh(self) -> bool:
        """Check whether credentials need refreshing.

        Returns:
            ``True`` if a refresh is required before the next
            request; ``False`` otherwise.
        """
        ...


class AuthState(BaseModel):
    """Tracks the runtime state of an authenticated session.

    Used by providers (primarily OAuth2) to persist and inspect
    the current credential lifecycle.

    Attributes:
        access_token: The current access token, if any.
        refresh_token: The current refresh token, if any.
        token_expiry: UTC expiry timestamp of *access_token*.
        scopes: Scopes granted by the authorization server.
        token_type: Token type string (typically ``"Bearer"``).
        is_authenticated: Whether the provider has valid credentials.
    """

    access_token: Optional[str] = Field(
        default=None,
        description="Current access token.",
    )
    refresh_token: Optional[str] = Field(
        default=None,
        description="Current refresh token for automatic renewal.",
    )
    token_expiry: Optional[datetime] = Field(
        default=None,
        description="UTC timestamp when the access token expires.",
    )
    scopes: list[str] = Field(
        default_factory=list,
        description="OAuth scopes granted for this session.",
    )
    token_type: str = Field(
        default="Bearer",
        description="Token type (typically 'Bearer').",
    )
    is_authenticated: bool = Field(
        default=False,
        description="Whether the provider currently holds valid credentials.",
    )
