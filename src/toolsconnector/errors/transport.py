"""Transport-level error subtree for network and connection failures."""

from __future__ import annotations

from typing import Any

from .base import ToolsConnectorError


class TransportError(ToolsConnectorError):
    """Base exception for network / transport failures.

    All transport errors default to ``retry_eligible=True`` because
    transient network issues are often resolved by retrying.
    """

    def __init__(
        self,
        message: str = "A transport-level error occurred.",
        *,
        connector: str = "",
        action: str | None = None,
        code: str = "TRANSPORT_CONNECTION_FAILED",
        retry_eligible: bool = True,
        retry_after_seconds: float | None = None,
        suggestion: str | None = "Check network connectivity and retry.",
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


class TimeoutError(TransportError):
    """The request timed out before a response was received."""

    def __init__(
        self,
        message: str = "Request timed out.",
        *,
        connector: str = "",
        action: str | None = None,
        code: str = "TRANSPORT_TIMEOUT",
        retry_eligible: bool = True,
        retry_after_seconds: float | None = None,
        suggestion: str | None = "Increase the timeout or retry. The upstream service may be slow.",
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


class ConnectionError(TransportError):
    """Failed to establish a connection to the upstream host."""

    def __init__(
        self,
        message: str = "Connection failed.",
        *,
        connector: str = "",
        action: str | None = None,
        code: str = "TRANSPORT_CONNECTION_FAILED",
        retry_eligible: bool = True,
        retry_after_seconds: float | None = None,
        suggestion: str
        | None = "Verify the host is reachable and that no firewall is blocking the connection.",
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


class DNSError(TransportError):
    """DNS resolution failed for the upstream host."""

    def __init__(
        self,
        message: str = "DNS resolution failed.",
        *,
        connector: str = "",
        action: str | None = None,
        code: str = "TRANSPORT_DNS_FAILED",
        retry_eligible: bool = True,
        retry_after_seconds: float | None = None,
        suggestion: str | None = "Verify the hostname is correct and that DNS is functioning.",
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
