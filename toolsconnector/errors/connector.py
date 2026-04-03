"""Connector lifecycle error subtree."""

from __future__ import annotations

from typing import Any

from .base import ToolsConnectorError


class ConnectorError(ToolsConnectorError):
    """Base exception for connector lifecycle failures."""

    def __init__(
        self,
        message: str = "A connector error occurred.",
        *,
        connector: str = "",
        action: str | None = None,
        code: str = "CONNECTOR_INIT_FAILED",
        retry_eligible: bool = False,
        retry_after_seconds: float | None = None,
        suggestion: str | None = "Review connector configuration and initialization.",
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


class ConnectorNotConfiguredError(ConnectorError):
    """The connector has not been configured with the required credentials or settings."""

    def __init__(
        self,
        message: str = "Connector is not configured.",
        *,
        connector: str = "",
        action: str | None = None,
        code: str = "CONNECTOR_NOT_CONFIGURED",
        retry_eligible: bool = False,
        retry_after_seconds: float | None = None,
        suggestion: str | None = "Provide the required credentials or configuration before using this connector.",
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


class ConnectorInitError(ConnectorError):
    """The connector failed during initialization (e.g. bad credentials, missing deps)."""

    def __init__(
        self,
        message: str = "Connector initialization failed.",
        *,
        connector: str = "",
        action: str | None = None,
        code: str = "CONNECTOR_INIT_FAILED",
        retry_eligible: bool = False,
        retry_after_seconds: float | None = None,
        suggestion: str | None = "Check that all required dependencies are installed and credentials are valid.",
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


class ActionNotFoundError(ConnectorError):
    """The requested action does not exist on this connector."""

    def __init__(
        self,
        message: str = "Action not found on this connector.",
        *,
        connector: str = "",
        action: str | None = None,
        code: str = "CONNECTOR_ACTION_NOT_FOUND",
        retry_eligible: bool = False,
        retry_after_seconds: float | None = None,
        suggestion: str | None = "Verify the action name. Use connector.list_actions() to see available actions.",
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
