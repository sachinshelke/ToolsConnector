"""Credential types for connector authentication."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from toolsconnector.spec.auth import AuthType


class CredentialSet(BaseModel):
    """Union of all credential types a connector may accept.

    Callers populate only the fields relevant to their chosen
    :class:`AuthType`.  The connector validates at init time that the
    required subset is present.

    Attributes:
        auth_type: The authentication strategy in use.
        api_key: API key string (for :attr:`AuthType.API_KEY`).
        bearer_token: Static bearer token.
        client_id: OAuth 2.0 client identifier.
        client_secret: OAuth 2.0 client secret.
        refresh_token: OAuth 2.0 refresh token for automatic renewal.
        access_token: OAuth 2.0 short-lived access token.
        token_expiry: Expiration timestamp of the current access token.
        username: Username for Basic authentication.
        password: Password for Basic authentication.
        service_account_json: Service account credentials as a JSON string
            or parsed dict.
        extra: Arbitrary additional credential fields for non-standard
            auth schemes.
    """

    auth_type: AuthType
    api_key: str | None = None
    bearer_token: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    refresh_token: str | None = None
    access_token: str | None = None
    token_expiry: datetime | None = None
    username: str | None = None
    password: str | None = None
    service_account_json: str | dict[str, Any] | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class OAuthConfig(BaseModel):
    """Runtime OAuth 2.0 configuration.

    This is the *runtime* counterpart to :class:`~toolsconnector.spec.auth.OAuthSpec`.
    While ``OAuthSpec`` lives in the connector's static specification,
    ``OAuthConfig`` is supplied by the caller at connect time with real
    client credentials and redirect URIs.

    Attributes:
        auth_url: Authorization endpoint URL.
        token_url: Token exchange endpoint URL.
        client_id: OAuth 2.0 client identifier.
        client_secret: OAuth 2.0 client secret.
        scopes: List of OAuth scope strings to request.
        redirect_uri: Redirect URI registered with the provider.
        extra_params: Additional query parameters to include in the
            authorization request.
    """

    auth_url: str
    token_url: str
    client_id: str
    client_secret: str
    scopes: list[str] = Field(default_factory=list)
    redirect_uri: str | None = None
    extra_params: dict[str, str] = Field(default_factory=dict)
