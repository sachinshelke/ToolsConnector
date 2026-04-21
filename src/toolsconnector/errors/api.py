"""API-level error subtree for upstream service failures."""

from __future__ import annotations

from typing import Any

from .base import ToolsConnectorError


class APIError(ToolsConnectorError):
    """Base exception for errors returned by an upstream API."""

    def __init__(
        self,
        message: str = "An API error occurred.",
        *,
        connector: str = "",
        action: str | None = None,
        code: str = "API_SERVER_ERROR",
        retry_eligible: bool = False,
        retry_after_seconds: float | None = None,
        suggestion: str | None = "Check the upstream service status page for details.",
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


class RateLimitError(APIError):
    """The upstream API returned a rate-limit / throttle response (HTTP 429)."""

    def __init__(
        self,
        message: str = "Rate limit exceeded.",
        *,
        connector: str = "",
        action: str | None = None,
        code: str = "API_RATE_LIMITED",
        retry_eligible: bool = True,
        retry_after_seconds: float | None = 60.0,
        suggestion: str | None = "Back off and retry after the indicated delay.",
        details: dict[str, Any] | None = None,
        upstream_status: int | None = 429,
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


class NotFoundError(APIError):
    """The requested resource was not found (HTTP 404)."""

    def __init__(
        self,
        message: str = "Resource not found.",
        *,
        connector: str = "",
        action: str | None = None,
        code: str = "API_NOT_FOUND",
        retry_eligible: bool = False,
        retry_after_seconds: float | None = None,
        suggestion: str | None = "Verify the resource ID or path is correct.",
        details: dict[str, Any] | None = None,
        upstream_status: int | None = 404,
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


class ValidationError(APIError):
    """The request payload failed upstream validation (HTTP 400/422)."""

    def __init__(
        self,
        message: str = "Request validation failed.",
        *,
        connector: str = "",
        action: str | None = None,
        code: str = "API_VALIDATION_FAILED",
        retry_eligible: bool = False,
        retry_after_seconds: float | None = None,
        suggestion: str | None = "Check the request parameters against the action schema.",
        details: dict[str, Any] | None = None,
        upstream_status: int | None = 422,
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


class ConflictError(APIError):
    """The request conflicts with the current state of the resource (HTTP 409)."""

    def __init__(
        self,
        message: str = "Resource conflict.",
        *,
        connector: str = "",
        action: str | None = None,
        code: str = "API_CONFLICT",
        retry_eligible: bool = False,
        retry_after_seconds: float | None = None,
        suggestion: str
        | None = "The resource may have been modified concurrently. Fetch the latest version and retry.",
        details: dict[str, Any] | None = None,
        upstream_status: int | None = 409,
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


class PermissionDeniedError(APIError):
    """The API denied permission for this request (HTTP 403)."""

    def __init__(
        self,
        message: str = "Permission denied by the upstream API.",
        *,
        connector: str = "",
        action: str | None = None,
        code: str = "API_PERMISSION_DENIED",
        retry_eligible: bool = False,
        retry_after_seconds: float | None = None,
        suggestion: str
        | None = "Ensure the authenticated user has permission to perform this action on the resource.",
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


class ServerError(APIError):
    """The upstream API returned a server-side error (HTTP 5xx)."""

    def __init__(
        self,
        message: str = "Upstream server error.",
        *,
        connector: str = "",
        action: str | None = None,
        code: str = "API_SERVER_ERROR",
        retry_eligible: bool = True,
        retry_after_seconds: float | None = None,
        suggestion: str
        | None = "The upstream service may be experiencing issues. Retry after a short delay.",
        details: dict[str, Any] | None = None,
        upstream_status: int | None = 500,
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
