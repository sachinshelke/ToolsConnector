"""Unit tests for toolsconnector.runtime.auth.oauth2.OAuth2Provider.

Focus: keystore key naming follows the ``{connector}:{tenant}:{type}``
convention (tenant id must not be hardcoded to ``"default"``).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import respx
from httpx import Response

from toolsconnector.keystore.memory import InMemoryKeyStore
from toolsconnector.runtime.auth.oauth2 import OAuth2Provider
from toolsconnector.spec.auth import AuthType
from toolsconnector.types.credentials import CredentialSet, OAuthConfig

_TOKEN_URL = "https://oauth2.example.com/token"


def _make_provider(
    keystore: InMemoryKeyStore,
    **kwargs: str,
) -> OAuth2Provider:
    return OAuth2Provider(
        oauth_config=OAuthConfig(
            auth_url="https://oauth2.example.com/auth",
            token_url=_TOKEN_URL,
            client_id="client-id",
            client_secret="client-secret",
        ),
        credentials=CredentialSet(
            auth_type=AuthType.OAUTH2,
            access_token="old-access",
            refresh_token="old-refresh",
            token_expiry=datetime.now(timezone.utc) - timedelta(minutes=5),
        ),
        keystore=keystore,
        **kwargs,
    )


class TestOAuth2KeystoreTenantKeys:
    """Refreshed tokens must persist under the caller's real tenant id."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_refresh_persists_under_real_tenant_id(self) -> None:
        """Keys are {connector}:{tenant}:{field}, not {connector}:default:*."""
        respx.post(_TOKEN_URL).mock(
            return_value=Response(
                200,
                json={
                    "access_token": "new-access",
                    "refresh_token": "new-refresh",
                    "expires_in": 3600,
                },
            ),
        )
        keystore = InMemoryKeyStore()
        provider = _make_provider(
            keystore,
            connector_name="gmail",
            tenant_id="user-123",
        )

        await provider.refresh()

        assert await keystore.get("gmail:user-123:access_token") == "new-access"
        assert await keystore.get("gmail:user-123:refresh_token") == "new-refresh"
        # Nothing may leak into the "default" tenant namespace.
        assert await keystore.get("gmail:default:access_token") is None
        assert await keystore.get("gmail:default:refresh_token") is None

    @pytest.mark.asyncio
    @respx.mock
    async def test_refresh_defaults_to_default_tenant(self) -> None:
        """Single-tenant callers keep the {connector}:default:* namespace."""
        respx.post(_TOKEN_URL).mock(
            return_value=Response(
                200,
                json={"access_token": "new-access", "expires_in": 3600},
            ),
        )
        keystore = InMemoryKeyStore()
        provider = _make_provider(keystore, connector_name="gmail")

        await provider.refresh()

        assert await keystore.get("gmail:default:access_token") == "new-access"

    @pytest.mark.asyncio
    @respx.mock
    async def test_two_tenants_do_not_collide(self) -> None:
        """Concurrent tenants refreshing the same connector stay isolated."""
        respx.post(_TOKEN_URL).mock(
            side_effect=[
                Response(200, json={"access_token": "access-alpha"}),
                Response(200, json={"access_token": "access-beta"}),
            ],
        )
        keystore = InMemoryKeyStore()
        provider_alpha = _make_provider(
            keystore,
            connector_name="gmail",
            tenant_id="tenant-alpha",
        )
        provider_beta = _make_provider(
            keystore,
            connector_name="gmail",
            tenant_id="tenant-beta",
        )

        await provider_alpha.refresh()
        await provider_beta.refresh()

        assert await keystore.get("gmail:tenant-alpha:access_token") == "access-alpha"
        assert await keystore.get("gmail:tenant-beta:access_token") == "access-beta"
