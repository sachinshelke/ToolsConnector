"""Pagination tests for the Calendly connector using respx.

Calendly pages with an opaque ``page_token``: each response carries
``pagination.next_page_token`` (``null`` on the last page), and the next
request sends it back as the ``page_token`` query parameter.

These tests pin that the connector walks those pages itself through
``anext_page()`` / ``collect()`` and keeps the caller's filters on every page.
They also cover ``list_webhooks``, which used to return a token without
accepting one, so it could never page.
"""

from __future__ import annotations

from typing import Optional

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.calendly import Calendly

_API = "https://api.calendly.com"
_USER = "https://api.calendly.com/users/U1"
_ORG = "https://api.calendly.com/organizations/O1"


@pytest_asyncio.fixture
async def calendly() -> Calendly:
    """Calendly connector with a fake personal access token."""
    connector = Calendly(credentials="fake-calendly-pat")
    await connector._setup()
    yield connector
    await connector._teardown()


def _page(uri: str, *, next_token: Optional[str]) -> dict:
    """One Calendly collection page holding a single resource."""
    return {
        "collection": [{"uri": uri, "name": uri.rsplit("/", 1)[-1]}],
        "pagination": {"count": 1, "next_page_token": next_token},
    }


@pytest.mark.asyncio
async def test_list_scheduled_events_anext_page_fetches_page_two(calendly: Calendly) -> None:
    """anext_page() must return page two, not None, with every filter kept.

    Fails without the `_fetch_next` wiring: returns None while has_more is True.
    """
    with respx.mock(base_url=_API) as respx_mock:
        route = respx_mock.get("/scheduled_events").mock(
            side_effect=[
                httpx.Response(200, json=_page(f"{_API}/scheduled_events/E1", next_token="TOK2")),
                httpx.Response(200, json=_page(f"{_API}/scheduled_events/E2", next_token=None)),
            ]
        )

        page1 = await calendly.alist_scheduled_events(
            user_uri=_USER, status="active", min_start_time="2026-09-01T00:00:00Z", limit=1
        )
        assert page1.has_more is True
        assert page1.page_state.cursor == "TOK2"

        page2 = await page1.anext_page()

        assert page2 is not None, "anext_page() returned None despite has_more=True"
        assert len(page2.items) == 1
        assert page2.has_more is False
        assert await page2.anext_page() is None

        # Dropping the status/time filters would page through every event.
        params = route.calls[1].request.url.params
        assert params["page_token"] == "TOK2"
        assert params["user"] == _USER
        assert params["status"] == "active"
        assert params["min_start_time"] == "2026-09-01T00:00:00Z"
        assert params["count"] == "1"


@pytest.mark.asyncio
async def test_list_event_types_collect_returns_every_page(calendly: Calendly) -> None:
    """collect() is the agent-facing path; it must span both pages.

    Fails without the wiring: returns 1 event type and looks complete.
    """
    with respx.mock(base_url=_API) as respx_mock:
        respx_mock.get("/event_types").mock(
            side_effect=[
                httpx.Response(200, json=_page(f"{_API}/event_types/T1", next_token="TOK2")),
                httpx.Response(200, json=_page(f"{_API}/event_types/T2", next_token=None)),
            ]
        )

        page1 = await calendly.alist_event_types(user_uri=_USER, limit=1)
        assert len(await page1.collect()) == 2


@pytest.mark.asyncio
async def test_list_webhooks_pages_via_page_token(calendly: Calendly) -> None:
    """list_webhooks must send the token back, keeping organization and scope.

    Fails before the fix twice over: there was no `page_token` parameter and no
    fetcher, so page two was unreachable by any route.
    """
    with respx.mock(base_url=_API) as respx_mock:
        route = respx_mock.get("/webhook_subscriptions").mock(
            side_effect=[
                httpx.Response(
                    200, json=_page(f"{_API}/webhook_subscriptions/W1", next_token="TOK2")
                ),
                httpx.Response(
                    200, json=_page(f"{_API}/webhook_subscriptions/W2", next_token=None)
                ),
            ]
        )

        page1 = await calendly.alist_webhooks(organization_uri=_ORG, scope="user")
        page2 = await page1.anext_page()

        assert page2 is not None, "anext_page() returned None despite has_more=True"
        assert len(page2.items) == 1
        params = route.calls[1].request.url.params
        assert params["page_token"] == "TOK2"
        assert params["organization"] == _ORG
        assert params["scope"] == "user"


@pytest.mark.asyncio
async def test_list_webhooks_accepts_page_token_for_manual_paging(calendly: Calendly) -> None:
    """Callers paging by hand must be able to pass the token back directly."""
    with respx.mock(base_url=_API) as respx_mock:
        route = respx_mock.get("/webhook_subscriptions").mock(
            return_value=httpx.Response(
                200, json=_page(f"{_API}/webhook_subscriptions/W2", next_token=None)
            )
        )

        await calendly.alist_webhooks(organization_uri=_ORG, page_token="TOK2")

        assert route.calls[0].request.url.params["page_token"] == "TOK2"
