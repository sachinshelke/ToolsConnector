"""Configuration error subtree."""

from __future__ import annotations

from typing import Any

from .base import ToolsConnectorError


class ConfigError(ToolsConnectorError):
    """Base exception for configuration-related failures."""

    def __init__(
        self,
        message: str = "A configuration error occurred.",
        *,
        connector: str = "",
        action: str | None = None,
        code: str = "CONFIG_INVALID",
        retry_eligible: bool = False,
        retry_after_seconds: float | None = None,
        suggestion: str | None = "Review the connector configuration.",
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


class InvalidConfigError(ConfigError):
    """The configuration value is present but invalid (wrong type, format, etc.)."""

    def __init__(
        self,
        message: str = "Invalid configuration value.",
        *,
        connector: str = "",
        action: str | None = None,
        code: str = "CONFIG_INVALID",
        retry_eligible: bool = False,
        retry_after_seconds: float | None = None,
        suggestion: str | None = "Check that the configuration values match the expected types and formats.",
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


class MissingConfigError(ConfigError):
    """A required configuration key is missing."""

    def __init__(
        self,
        message: str = "Required configuration key is missing.",
        *,
        connector: str = "",
        action: str | None = None,
        code: str = "CONFIG_MISSING_REQUIRED",
        retry_eligible: bool = False,
        retry_after_seconds: float | None = None,
        suggestion: str | None = "Provide all required configuration keys before initializing the connector.",
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
