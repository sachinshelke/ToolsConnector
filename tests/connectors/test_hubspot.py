"""Pagination tests for the HubSpot connector using respx.

HubSpot CRM v3 pages with an opaque ``after`` cursor returned under
``paging.next.after``. List endpoints take it as a query parameter; the search
endpoint takes it in the POST body.

These tests pin that the connector walks those pages itself through
``anext_page()`` / ``collect()``. They also cover ``search_contacts``, which
used to return a cursor without accepting one, so it could never page at all.
"""

from __future__ import annotations

import json
from typing import Optional

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.hubspot import HubSpot

_API = "https://api.hubapi.com"


@pytest_asyncio.fixture
async def hubspot() -> HubSpot:
    """HubSpot connector with a fake private-app token."""
    connector = HubSpot(credentials="pat-na1-fake-token")
    await connector._setup()
    yield connector
    await connector._teardown()


def _contacts_page(contact_id: str, *, after: Optional[str]) -> dict:
    """One CRM v3 contacts page holding a single contact."""
    page: dict = {
        "results": [
            {
                "id": contact_id,
                "properties": {"email": f"{contact_id}@acme.test"},
                "createdAt": "2026-09-01T00:00:00Z",
                "updatedAt": "2026-09-01T00:00:00Z",
                "archived": False,
            }
        ]
    }
    if after is not None:
        page["paging"] = {"next": {"after": after, "link": "ignored"}}
    return page


@pytest.mark.asyncio
async def test_list_contacts_anext_page_fetches_page_two(hubspot: HubSpot) -> None:
    """anext_page() must return page two, not None.

    Fails without the `_fetch_next` wiring: returns None while has_more is True.
    """
    with respx.mock(base_url=_API) as respx_mock:
        route = respx_mock.get("/crm/v3/objects/contacts").mock(
            side_effect=[
                httpx.Response(200, json=_contacts_page("101", after="AFTER_2")),
                httpx.Response(200, json=_contacts_page("102", after=None)),
            ]
        )

        page1 = await hubspot.alist_contacts(limit=1)
        assert page1.has_more is True
        assert page1.page_state.cursor == "AFTER_2"

        page2 = await page1.anext_page()

        assert page2 is not None, "anext_page() returned None despite has_more=True"
        assert [c.id for c in page2.items] == ["102"]
        assert page2.has_more is False
        assert await page2.anext_page() is None

        params = route.calls[1].request.url.params
        assert params["after"] == "AFTER_2"
        assert params["limit"] == "1"


@pytest.mark.asyncio
async def test_list_contacts_collect_returns_every_page(hubspot: HubSpot) -> None:
    """collect() is the agent-facing path; it must span both pages.

    Fails without the wiring: returns 1 contact and looks complete.
    """
    with respx.mock(base_url=_API) as respx_mock:
        respx_mock.get("/crm/v3/objects/contacts").mock(
            side_effect=[
                httpx.Response(200, json=_contacts_page("101", after="AFTER_2")),
                httpx.Response(200, json=_contacts_page("102", after=None)),
            ]
        )

        page1 = await hubspot.alist_contacts(limit=1)
        assert [c.id for c in await page1.collect()] == ["101", "102"]


@pytest.mark.asyncio
async def test_search_contacts_pages_via_after_in_body(hubspot: HubSpot) -> None:
    """search_contacts must send the cursor back in the POST body, with the query.

    Fails before the fix twice over: there was no `after` parameter, and no
    fetcher, so page two was unreachable by any route.
    """
    with respx.mock(base_url=_API) as respx_mock:
        route = respx_mock.post("/crm/v3/objects/contacts/search").mock(
            side_effect=[
                httpx.Response(200, json={**_contacts_page("201", after="AFTER_2"), "total": 2}),
                httpx.Response(200, json={**_contacts_page("202", after=None), "total": 2}),
            ]
        )

        page1 = await hubspot.asearch_contacts(query="acme", limit=1)
        assert page1.has_more is True
        assert page1.total_count == 2

        page2 = await page1.anext_page()

        assert page2 is not None, "anext_page() returned None despite has_more=True"
        assert [c.id for c in page2.items] == ["202"]

        first = json.loads(route.calls[0].request.read())
        second = json.loads(route.calls[1].request.read())
        assert "after" not in first
        assert second == {"query": "acme", "limit": 1, "after": "AFTER_2"}


@pytest.mark.asyncio
async def test_search_contacts_accepts_after_for_manual_paging(hubspot: HubSpot) -> None:
    """Callers paging by hand must be able to pass the cursor back directly."""
    with respx.mock(base_url=_API) as respx_mock:
        route = respx_mock.post("/crm/v3/objects/contacts/search").mock(
            return_value=httpx.Response(200, json=_contacts_page("202", after=None))
        )

        page = await hubspot.asearch_contacts(query="acme", limit=1, after="AFTER_2")

        assert [c.id for c in page.items] == ["202"]
        assert json.loads(route.calls[0].request.read())["after"] == "AFTER_2"
