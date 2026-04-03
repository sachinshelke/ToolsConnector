"""Auth specification types."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class AuthType(str, Enum):
    """Supported authentication methods.

    Each connector declares which auth types it supports.
    The runtime selects the appropriate AuthProvider at init time.
    """

    API_KEY = "api_key"
    BEARER_TOKEN = "bearer_token"
    BASIC = "basic"
    OAUTH2 = "oauth2"
    OAUTH2_PKCE = "oauth2_pkce"
    OIDC = "oidc"
    SERVICE_ACCOUNT = "service_account"
    HMAC = "hmac"
    AWS_SIGV4 = "aws_sigv4"
    MTLS = "mtls"
    CUSTOM = "custom"


class ScopeSet(BaseModel):
    """A named set of OAuth scopes.

    Example:
        ScopeSet(name="read", scopes=["gmail.readonly"])
        ScopeSet(name="full", scopes=["gmail.modify"])
    """

    name: str = Field(description="Human-readable scope set name (e.g., 'read', 'send').")
    scopes: list[str] = Field(description="OAuth scope strings for this set.")


class OAuthSpec(BaseModel):
    """OAuth 2.0 configuration for a connector."""

    auth_url: str = Field(description="Authorization endpoint URL.")
    token_url: str = Field(description="Token exchange endpoint URL.")
    scopes: list[ScopeSet] = Field(
        default_factory=list,
        description="Named scope sets (e.g., read, write, full).",
    )
    supports_pkce: bool = Field(
        default=False,
        description="Whether this provider supports PKCE.",
    )
    supports_refresh: bool = Field(
        default=True,
        description="Whether refresh tokens are supported.",
    )
    extra_params: dict[str, str] = Field(
        default_factory=dict,
        description="Provider-specific extra parameters for auth URL.",
    )


class ServiceAccountSpec(BaseModel):
    """Service account configuration for a connector."""

    credential_format: str = Field(
        default="json_keyfile",
        description="Expected credential format (e.g., 'json_keyfile', 'pem').",
    )
    scopes: list[str] = Field(
        default_factory=list,
        description="Default scopes for service account.",
    )


class APIKeySpec(BaseModel):
    """API key configuration for a connector."""

    location: str = Field(
        default="header",
        description="Where to send the key: 'header', 'query', or 'body'.",
    )
    param_name: str = Field(
        default="Authorization",
        description="Header name or query parameter name for the key.",
    )
    prefix: Optional[str] = Field(
        default=None,
        description="Prefix before the key value (e.g., 'Bearer', 'Token').",
    )


class AuthProviderSpec(BaseModel):
    """Specification for a single supported auth method on a connector."""

    type: AuthType
    oauth: Optional[OAuthSpec] = None
    service_account: Optional[ServiceAccountSpec] = None
    api_key: Optional[APIKeySpec] = None
    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific auth configuration.",
    )


class AuthSpec(BaseModel):
    """Complete auth specification for a connector."""

    supported: list[AuthProviderSpec] = Field(
        default_factory=list,
        description="List of supported authentication methods.",
    )
    default: Optional[AuthType] = Field(
        default=None,
        description="Default auth type if multiple are supported.",
    )
