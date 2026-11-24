"""Pagination tests for the Confluence (Cloud REST v2) connector using respx.

Confluence v2 does not hand back a bare cursor. ``_links.next`` is a relative
URL, for example ``/wiki/api/v2/spaces/42/pages?cursor=eyJ...&limit=1``, and the
next request needs only its ``cursor`` query parameter. The connector used to
store the whole URL as ``page_state.cursor``, so feeding it back sent
``?cursor=/wiki/api/v2/...``, and it never wired ``_fetch_next`` at all.

These tests pin that ``page_state.cursor`` is the real cursor and that the
connector walks pages itself through ``anext_page()`` / ``collect()``.
"""

from __future__ import annotations

from typing import Optional

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.confluence import Confluence
from toolsconnector.errors import PaginationNotWiredError

_API = "https://acme.atlassian.net/wiki/api/v2"


@pytest_asyncio.fixture
async def confluence() -> Confluence:
    """Confluence connector with fake Basic-auth credentials."""
    connector = Confluence(credentials="bot@acme.test:fake-api-token", base_url=_API)
    await connector._setup()
    yield connector
    await connector._teardown()


def _page(item_id: str, *, next_link: Optional[str]) -> dict:
    """One v2 list response holding a single page, shaped like the real API."""
    body: dict = {
        "results": [{"id": item_id, "title": f"Page {item_id}", "status": "current"}],
        "_links": {"base": "https://acme.atlassian.net/wiki"},
    }
    if next_link is not None:
        body["_links"]["next"] = next_link
    return body


# ---------------------------------------------------------------------------
# _cursor_from_next_link
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("next_link", "expected"),
    [
        ("/wiki/api/v2/pages?cursor=CUR2&limit=25", "CUR2"),
        ("/wiki/api/v2/pages?limit=25&cursor=a%2Bb%3D", "a+b="),  # URL-decoded
        ("BARE_CURSOR", "BARE_CURSOR"),  # no query string: already a cursor
        ("/wiki/api/v2/pages?limit=25", None),  # link with no cursor param
        (None, None),
        ("", None),
    ],
)
def test_cursor_from_next_link(next_link: Optional[str], expected: Optional[str]) -> None:
    # Imported here so a missing helper fails only this test, not the whole module.
    from toolsconnector.connectors.confluence.connector import _cursor_from_next_link

    assert _cursor_from_next_link(next_link) == expected


# ---------------------------------------------------------------------------
# Walking pages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_pages_sends_the_cursor_not_the_next_url(confluence: Confluence) -> None:
    """page two must be requested with cursor=CUR2, and anext_page() must work.

    Fails on the old code twice over: page_state.cursor was the whole relative
    URL, and anext_page() returned None because nothing was wired.
    """
    with respx.mock(base_url=_API) as respx_mock:
        route = respx_mock.get("/spaces/42/pages").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json=_page("1", next_link="/wiki/api/v2/spaces/42/pages?cursor=CUR2&limit=1"),
                ),
                httpx.Response(200, json=_page("2", next_link=None)),
            ]
        )

        page1 = await confluence.alist_pages(space_id="42", limit=1)
        assert page1.has_more is True
        assert page1.page_state.cursor == "CUR2"

        page2 = await page1.anext_page()

        assert page2 is not None, "anext_page() returned None despite has_more=True"
        assert [p.id for p in page2.items] == ["2"]
        assert page2.has_more is False
        assert await page2.anext_page() is None

        params = route.calls[1].request.url.params
        assert params["cursor"] == "CUR2"
        assert params["limit"] == "1"


@pytest.mark.asyncio
async def test_list_spaces_collect_returns_every_page(confluence: Confluence) -> None:
    """collect() is the agent-facing path; it must span all pages.

    Fails without the wiring: returns 1 space and looks complete.
    """
    with respx.mock(base_url=_API) as respx_mock:
        respx_mock.get("/spaces").mock(
            side_effect=[
                httpx.Response(200, json=_page("S1", next_link="/wiki/api/v2/spaces?cursor=C2")),
                httpx.Response(200, json=_page("S2", next_link="/wiki/api/v2/spaces?cursor=C3")),
                httpx.Response(200, json=_page("S3", next_link=None)),
            ]
        )

        page1 = await confluence.alist_spaces(limit=1)
        assert [s.id for s in await page1.collect()] == ["S1", "S2", "S3"]


@pytest.mark.asyncio
async def test_next_link_without_cursor_stays_loud(confluence: Confluence) -> None:
    """A next link we can't extract a cursor from must raise, not look complete."""
    with respx.mock(base_url=_API) as respx_mock:
        respx_mock.get("/spaces").mock(
            return_value=httpx.Response(
                200, json=_page("S1", next_link="/wiki/api/v2/spaces?limit=1")
            )
        )

        page = await confluence.alist_spaces(limit=1)
        assert page.has_more is True
        assert page.page_state.cursor is None

        with pytest.raises(PaginationNotWiredError):
            await page.anext_page()
