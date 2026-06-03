"""Regression test for Twilio ``next_page_uri`` pagination.

Surfaced by the multi-language SDK spike (``experiments/sdk_spike``):
``_fetch_msgs`` / ``_fetch_calls`` GET the server-returned ``next_page_uri`` (a
version-prefixed absolute path) against a ``base_url`` that already carries the
``/2010-04-01`` prefix. httpx merges ``base_url`` by *concatenation*, so the
second page's path was doubled (``/2010-04-01/2010-04-01/...``) and would 404.
"""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.twilio import Twilio

SID = "ACfake"


@pytest_asyncio.fixture
async def twilio() -> Twilio:
    connector = Twilio(credentials=f"{SID}:secrettoken")
    await connector._setup()
    yield connector
    await connector._teardown()


@pytest.mark.asyncio
async def test_list_messages_pagination_does_not_double_prefix(twilio: Twilio) -> None:
    """Following ``next_page_uri`` keeps a single ``/2010-04-01`` prefix."""
    path = f"/2010-04-01/Accounts/{SID}/Messages.json"
    page1 = {
        "messages": [{"sid": "SM1"}],
        "next_page_uri": f"{path}?PageSize=1&Page=1&PageToken=PAxyz",
    }
    page2 = {"messages": [{"sid": "SM2"}], "next_page_uri": None}

    with respx.mock(base_url="https://api.twilio.com", assert_all_called=True) as mock:
        # A single route at the SINGLE-prefixed path serves both pages. Pre-fix,
        # the second request hit /2010-04-01/2010-04-01/... and would NOT match
        # this route — so this test fails loudly on the regression.
        route = mock.get(path).mock(
            side_effect=[
                httpx.Response(200, json=page1),
                httpx.Response(200, json=page2),
            ]
        )

        first = await twilio.alist_messages(limit=1)
        second = await first.anext_page()

        assert route.call_count == 2
        req2 = route.calls[1].request
        assert req2.url.path == path
        assert "/2010-04-01/2010-04-01/" not in str(req2.url)
        assert [m.sid for m in second.items] == ["SM2"]
