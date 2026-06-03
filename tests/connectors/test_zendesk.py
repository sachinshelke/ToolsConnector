"""Regression test for the Zendesk connector base-URL ``{subdomain}`` substitution.

Surfaced by the multi-language SDK spike (``experiments/sdk_spike``): same dead
``.format`` bug class as Shopify — requests targeted the literal host
``{subdomain}.zendesk.com``.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from toolsconnector.connectors.zendesk import Zendesk


@pytest_asyncio.fixture
async def zendesk() -> Zendesk:
    """Credentials are ``email:api_token:subdomain``."""
    connector = Zendesk(credentials="agent@example.com:faketoken:acme")
    await connector._setup()
    yield connector
    await connector._teardown()


@pytest.mark.asyncio
async def test_base_url_substitutes_subdomain_from_credentials(zendesk: Zendesk) -> None:
    assert zendesk._client.base_url.host == "acme.zendesk.com"
    assert "{subdomain}" not in str(zendesk._client.base_url)
