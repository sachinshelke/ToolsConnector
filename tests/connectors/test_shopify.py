"""Regression tests for the Shopify connector.

Surfaced by the multi-language SDK spike (``experiments/sdk_spike``): the
``{store}`` base-URL template was never substituted in normal BYOK construction.
``BaseConnector.__init__`` pre-fills ``_base_url`` with the class template, so
``Shopify._setup``'s ``.format(store=...)`` branch was dead code and every
request targeted the literal host ``{store}.myshopify.com`` (DNS failure).
"""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.shopify import Shopify


@pytest_asyncio.fixture
async def shopify() -> Shopify:
    """Shopify connector built the documented way: ``access_token:store``."""
    connector = Shopify(credentials="shpat_fake_token:mystore")
    await connector._setup()
    yield connector
    await connector._teardown()


@pytest.mark.asyncio
async def test_base_url_substitutes_store_from_credentials(shopify: Shopify) -> None:
    """{store} is resolved from credentials, never left literal."""
    assert shopify._client.base_url.host == "mystore.myshopify.com"
    assert "{store}" not in str(shopify._client.base_url)


@pytest.mark.asyncio
async def test_request_targets_resolved_store_host(shopify: Shopify) -> None:
    """An actual request hits the resolved store host with the access token."""
    with respx.mock(base_url="https://mystore.myshopify.com", assert_all_called=True) as mock:
        route = mock.get("/admin/api/2024-01/products.json").mock(
            return_value=httpx.Response(200, json={"products": []})
        )
        await shopify.alist_products(limit=10)
        req = route.calls.last.request
        assert req.url.host == "mystore.myshopify.com"
        assert req.headers["x-shopify-access-token"] == "shpat_fake_token"
