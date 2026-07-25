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


# ---------------------------------------------------------------------------
# Declaration helpers
#
# A connector declares how it is authenticated so that callers -- especially
# platforms rendering a "connect your tools" form -- can discover the exact
# credential shape instead of parsing prose. Each helper returns the
# ``_auth_providers_config`` list a connector assigns as a class attribute.
#
# ``extra`` carries the platform-facing contract:
#   credential_format  "string" | "delimited" | "json" | "none"
#   fields             [{name, label, required, secret, help}]
#   separator/order    how to join the fields (delimited format only)
#   obtain_url         where the user gets the credential
#   scopes             permissions the credential needs
# ``env_var`` is added automatically by ``BaseConnector.get_spec()``.
# ---------------------------------------------------------------------------


def _field(
    name: str,
    label: str,
    *,
    required: bool = True,
    secret: bool = True,
    hint: str = "",
) -> dict[str, Any]:
    """Build one credential-form field descriptor."""
    return {
        "name": name,
        "label": label,
        "required": required,
        "secret": secret,
        "help": hint,
    }


def _extra(
    credential_format: str,
    fields: list[dict[str, Any]],
    obtain_url: str,
    docs_url: str,
    scopes: Optional[list[str]],
    **rest: Any,
) -> dict[str, Any]:
    extra: dict[str, Any] = {
        "credential_format": credential_format,
        "fields": fields,
    }
    if obtain_url:
        extra["obtain_url"] = obtain_url
    if docs_url:
        extra["docs_url"] = docs_url
    if scopes:
        extra["scopes"] = scopes
    extra.update(rest)
    return extra


def bearer_auth(
    *,
    label: str = "API token",
    hint: str = "",
    obtain_url: str = "",
    docs_url: str = "",
    scopes: Optional[list[str]] = None,
    field_name: str = "token",
) -> list[AuthProviderSpec]:
    """Declare ``Authorization: Bearer <token>`` with a single token value."""
    return [
        AuthProviderSpec(
            type=AuthType.BEARER_TOKEN,
            api_key=APIKeySpec(location="header", param_name="Authorization", prefix="Bearer"),
            extra=_extra(
                "string",
                [_field(field_name, label, hint=hint)],
                obtain_url,
                docs_url,
                scopes,
            ),
        )
    ]


def header_key_auth(
    header: str,
    *,
    label: str = "API key",
    hint: str = "",
    prefix: Optional[str] = None,
    obtain_url: str = "",
    docs_url: str = "",
    scopes: Optional[list[str]] = None,
    field_name: str = "api_key",
) -> list[AuthProviderSpec]:
    """Declare a single credential sent in a custom header."""
    return [
        AuthProviderSpec(
            type=AuthType.API_KEY,
            api_key=APIKeySpec(location="header", param_name=header, prefix=prefix),
            extra=_extra(
                "string",
                [_field(field_name, label, hint=hint)],
                obtain_url,
                docs_url,
                scopes,
            ),
        )
    ]


def delimited_auth(
    fields: list[dict[str, Any]],
    *,
    auth_type: AuthType = AuthType.BASIC,
    header: str = "Authorization",
    prefix: Optional[str] = None,
    separator: str = ":",
    obtain_url: str = "",
    docs_url: str = "",
    scopes: Optional[list[str]] = None,
) -> list[AuthProviderSpec]:
    """Declare several values joined by a separator into one credential string.

    The caller collects each field, joins them with ``separator`` in the
    declared ``order``, and passes the result as the credential.
    """
    return [
        AuthProviderSpec(
            type=auth_type,
            api_key=APIKeySpec(location="header", param_name=header, prefix=prefix),
            extra=_extra(
                "delimited",
                fields,
                obtain_url,
                docs_url,
                scopes,
                separator=separator,
                order=[f["name"] for f in fields],
            ),
        )
    ]


def query_key_auth(
    fields: list[dict[str, Any]],
    *,
    separator: str = ":",
    obtain_url: str = "",
    docs_url: str = "",
) -> list[AuthProviderSpec]:
    """Declare credentials sent as query parameters."""
    return [
        AuthProviderSpec(
            type=AuthType.API_KEY,
            api_key=APIKeySpec(location="query", param_name=fields[0]["name"]),
            extra=_extra(
                "delimited" if len(fields) > 1 else "string",
                fields,
                obtain_url,
                docs_url,
                None,
                separator=separator,
                order=[f["name"] for f in fields],
            ),
        )
    ]


def aws_sigv4_auth(*, service: str = "", docs_url: str = "") -> list[AuthProviderSpec]:
    """Declare AWS SigV4 request signing (keys resolved by the AWS chain)."""
    return [
        AuthProviderSpec(
            type=AuthType.AWS_SIGV4,
            extra=_extra(
                "delimited",
                [
                    _field("access_key_id", "AWS access key ID", secret=False),
                    _field("secret_access_key", "AWS secret access key"),
                    _field(
                        "region",
                        "AWS region",
                        required=False,
                        secret=False,
                        hint="Defaults to the connector's configured region.",
                    ),
                ],
                "https://console.aws.amazon.com/iam/",
                docs_url,
                None,
                separator=":",
                order=["access_key_id", "secret_access_key", "region"],
                service=service,
                note=(
                    "Credentials may also be omitted and resolved from the"
                    " standard AWS environment/instance-role chain."
                ),
            ),
        )
    ]


def service_account_auth(
    *, scopes: Optional[list[str]] = None, docs_url: str = ""
) -> list[AuthProviderSpec]:
    """Declare a Google OAuth2 access token / service-account credential."""
    return [
        AuthProviderSpec(
            type=AuthType.OAUTH2,
            api_key=APIKeySpec(location="header", param_name="Authorization", prefix="Bearer"),
            extra=_extra(
                "string",
                [
                    _field(
                        "access_token",
                        "Google OAuth2 access token",
                        hint=(
                            "Obtain via your own Google OAuth consent flow or a"
                            " service account; the library never stores it."
                        ),
                    )
                ],
                "https://console.cloud.google.com/apis/credentials",
                docs_url,
                scopes,
            ),
        )
    ]


def custom_auth(
    fields: list[dict[str, Any]],
    *,
    credential_format: str = "json",
    obtain_url: str = "",
    docs_url: str = "",
    scopes: Optional[list[str]] = None,
    **rest: Any,
) -> list[AuthProviderSpec]:
    """Declare a connector-specific credential shape."""
    return [
        AuthProviderSpec(
            type=AuthType.CUSTOM,
            extra=_extra(credential_format, fields, obtain_url, docs_url, scopes, **rest),
        )
    ]


def no_auth(*, hint: str = "No credentials required.") -> list[AuthProviderSpec]:
    """Declare that a connector needs no credentials at all."""
    return [
        AuthProviderSpec(
            type=AuthType.CUSTOM,
            extra={"credential_format": "none", "fields": [], "help": hint},
        )
    ]


auth_field = _field
