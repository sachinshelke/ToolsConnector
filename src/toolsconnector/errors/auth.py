"""Authentication and authorization error subtree."""

from __future__ import annotations

from typing import Any

from .base import ToolsConnectorError


class AuthError(ToolsConnectorError):
    """Base exception for all authentication / authorization failures."""

    def __init__(
        self,
        message: str = "Authentication failed.",
        *,
        connector: str = "",
        action: str | None = None,
        code: str = "AUTH_INVALID_CREDENTIALS",
        retry_eligible: bool = False,
        retry_after_seconds: float | None = None,
        suggestion: str | None = "Check your credentials and try again.",
        details: dict[str, Any] | None = None,
        upstream_status: int | None = None,
    ) -> None:
        super().__init__(
            message,
            connector=connector,
            action=action,
            code=code,
            retry_eligible=retry_eligible,
            retry_after_seconds=retry_after_seconds,
            suggestion=suggestion,
            details=details,
            upstream_status=upstream_status,
        )


class TokenExpiredError(AuthError):
    """The access token has expired and must be refreshed or re-issued."""

    def __init__(
        self,
        message: str = "Access token has expired.",
        *,
        connector: str = "",
        action: str | None = None,
        code: str = "AUTH_TOKEN_EXPIRED",
        retry_eligible: bool = True,
        retry_after_seconds: float | None = None,
        suggestion: str
        | None = "Re-authenticate or refresh the token to obtain a new access token.",
        details: dict[str, Any] | None = None,
        upstream_status: int | None = 401,
    ) -> None:
        super().__init__(
            message,
            connector=connector,
            action=action,
            code=code,
            retry_eligible=retry_eligible,
            retry_after_seconds=retry_after_seconds,
            suggestion=suggestion,
            details=details,
            upstream_status=upstream_status,
        )


class InvalidCredentialsError(AuthError):
    """The provided credentials (API key, username/password, etc.) are invalid."""

    def __init__(
        self,
        message: str = "Invalid credentials provided.",
        *,
        connector: str = "",
        action: str | None = None,
        code: str = "AUTH_INVALID_CREDENTIALS",
        retry_eligible: bool = False,
        retry_after_seconds: float | None = None,
        suggestion: str
        | None = "Verify that the API key or credentials are correct and have not been revoked.",
        details: dict[str, Any] | None = None,
        upstream_status: int | None = 401,
    ) -> None:
        super().__init__(
            message,
            connector=connector,
            action=action,
            code=code,
            retry_eligible=retry_eligible,
            retry_after_seconds=retry_after_seconds,
            suggestion=suggestion,
            details=details,
            upstream_status=upstream_status,
        )


class InsufficientScopeError(AuthError):
    """The credentials are valid but lack the required scopes / permissions."""

    def __init__(
        self,
        message: str = "Insufficient scope for the requested action.",
        *,
        connector: str = "",
        action: str | None = None,
        code: str = "AUTH_INSUFFICIENT_SCOPE",
        retry_eligible: bool = False,
        retry_after_seconds: float | None = None,
        suggestion: str | None = "Request additional OAuth scopes or permissions for this action.",
        details: dict[str, Any] | None = None,
        upstream_status: int | None = 403,
    ) -> None:
        super().__init__(
            message,
            connector=connector,
            action=action,
            code=code,
            retry_eligible=retry_eligible,
            retry_after_seconds=retry_after_seconds,
            suggestion=suggestion,
            details=details,
            upstream_status=upstream_status,
        )


class RefreshFailedError(AuthError):
    """An attempt to refresh the access token failed."""

    def __init__(
        self,
        message: str = "Token refresh failed.",
        *,
        connector: str = "",
        action: str | None = None,
        code: str = "AUTH_REFRESH_FAILED",
        retry_eligible: bool = False,
        retry_after_seconds: float | None = None,
        suggestion: str
        | None = "The refresh token may be expired or revoked. Re-authenticate from scratch.",
        details: dict[str, Any] | None = None,
        upstream_status: int | None = None,
    ) -> None:
        super().__init__(
            message,
            connector=connector,
            action=action,
            code=code,
            retry_eligible=retry_eligible,
            retry_after_seconds=retry_after_seconds,
            suggestion=suggestion,
            details=details,
            upstream_status=upstream_status,
        )
