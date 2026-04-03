"""Error specification types."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ErrorCode(str, Enum):
    """Machine-readable error codes used across all connectors.

    Organized by category prefix:
    - AUTH_*      — credential/token/scope failures
    - API_*       — upstream API returned an error
    - TRANSPORT_* — network/connection issues
    - CONNECTOR_* — connector lifecycle issues
    - CONFIG_*    — invalid configuration
    """

    # Auth errors
    AUTH_TOKEN_EXPIRED = "AUTH_TOKEN_EXPIRED"
    AUTH_INVALID_CREDENTIALS = "AUTH_INVALID_CREDENTIALS"
    AUTH_INSUFFICIENT_SCOPE = "AUTH_INSUFFICIENT_SCOPE"
    AUTH_REFRESH_FAILED = "AUTH_REFRESH_FAILED"
    AUTH_MFA_REQUIRED = "AUTH_MFA_REQUIRED"
    AUTH_PROVIDER_ERROR = "AUTH_PROVIDER_ERROR"

    # API errors
    API_RATE_LIMITED = "API_RATE_LIMITED"
    API_NOT_FOUND = "API_NOT_FOUND"
    API_VALIDATION_FAILED = "API_VALIDATION_FAILED"
    API_CONFLICT = "API_CONFLICT"
    API_PERMISSION_DENIED = "API_PERMISSION_DENIED"
    API_SERVER_ERROR = "API_SERVER_ERROR"
    API_DEPRECATED = "API_DEPRECATED"
    API_UNAVAILABLE = "API_UNAVAILABLE"

    # Transport errors
    TRANSPORT_TIMEOUT = "TRANSPORT_TIMEOUT"
    TRANSPORT_CONNECTION_FAILED = "TRANSPORT_CONNECTION_FAILED"
    TRANSPORT_DNS_FAILED = "TRANSPORT_DNS_FAILED"
    TRANSPORT_SSL_ERROR = "TRANSPORT_SSL_ERROR"

    # Connector errors
    CONNECTOR_NOT_CONFIGURED = "CONNECTOR_NOT_CONFIGURED"
    CONNECTOR_INIT_FAILED = "CONNECTOR_INIT_FAILED"
    CONNECTOR_ACTION_NOT_FOUND = "CONNECTOR_ACTION_NOT_FOUND"
    CONNECTOR_PROTOCOL_ERROR = "CONNECTOR_PROTOCOL_ERROR"

    # Config errors
    CONFIG_INVALID = "CONFIG_INVALID"
    CONFIG_MISSING_REQUIRED = "CONFIG_MISSING_REQUIRED"

    # Unknown
    UNKNOWN = "UNKNOWN"


class ErrorSpec(BaseModel):
    """Specification for an error that a connector action can produce."""

    code: ErrorCode
    description: str = Field(
        default="",
        description="Human-readable description of this error.",
    )
    retry_eligible: bool = Field(
        default=False,
        description="Whether this error is eligible for automatic retry.",
    )
    suggestion: Optional[str] = Field(
        default=None,
        description="Actionable suggestion for resolving this error.",
    )
