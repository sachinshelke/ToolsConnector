"""Regression test for the Mailchimp connector base-URL ``{dc}`` substitution.

Surfaced by the multi-language SDK spike (``experiments/sdk_spike``): same dead
``.format`` bug class as Shopify — ``BaseConnector.__init__`` pre-fills
``_base_url`` with the class template, so the ``{dc}`` branch never ran and
requests targeted the literal host ``{dc}.api.mailchimp.com``.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from toolsconnector.connectors.mailchimp import Mailchimp


@pytest_asyncio.fixture
async def mailchimp() -> Mailchimp:
    """Datacenter is parsed from the API-key suffix (``...-us21`` → ``us21``)."""
    connector = Mailchimp(credentials="fakekey-us21")
    await connector._setup()
    yield connector
    await connector._teardown()


@pytest.mark.asyncio
async def test_base_url_substitutes_dc_from_api_key(mailchimp: Mailchimp) -> None:
    assert mailchimp._client.base_url.host == "us21.api.mailchimp.com"
    assert "{dc}" not in str(mailchimp._client.base_url)
