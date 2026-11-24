"""Pagination tests for the Jira connector using respx.

Jira pages by offset (``startAt`` / ``maxResults``), with two different
"is there more?" signals: the core REST API reports ``total`` (more exists while
``startAt + returned < total``), and the Agile API reports ``isLast``.

These tests pin that the connector walks those pages itself through
``anext_page()`` / ``collect()``, keeps the caller's filters on every page, and
never loops on a page that claims more but advances nothing.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from toolsconnector.connectors.jira import Jira
from toolsconnector.errors import PaginationNotWiredError

_SITE = "https://acme.atlassian.net"


@pytest.fixture
def jira() -> Jira:
    """Jira connector with fake Basic-auth credentials.

    Every request opens its own httpx client, so respx intercepts without any
    setup/teardown.
    """
    return Jira(credentials="bot@acme.test:fake-api-token", base_url=f"{_SITE}/rest/api/3")


def _search_page(key: str, *, start_at: int, total: int) -> dict:
    """One core-API /search response holding a single issue."""
    return {
        "startAt": start_at,
        "maxResults": 1,
        "total": total,
        "issues": [{"id": key.split("-")[1], "key": key, "fields": {}}],
    }


@pytest.mark.asyncio
async def test_search_issues_anext_page_fetches_page_two(jira: Jira) -> None:
    """anext_page() must return page two, not None.

    Fails without the `_fetch_next` wiring: returns None while has_more is True.
    """
    with respx.mock(base_url=f"{_SITE}/rest/api/3") as respx_mock:
        route = respx_mock.get("/search").mock(
            side_effect=[
                httpx.Response(200, json=_search_page("ENG-1", start_at=0, total=2)),
                httpx.Response(200, json=_search_page("ENG-2", start_at=1, total=2)),
            ]
        )

        page1 = await jira.asearch_issues(jql="project = ENG", limit=1)
        assert page1.has_more is True
        assert page1.page_state.offset == 1

        page2 = await page1.anext_page()

        assert page2 is not None, "anext_page() returned None despite has_more=True"
        assert [i.key for i in page2.items] == ["ENG-2"]
        assert page2.has_more is False
        assert await page2.anext_page() is None

        # The follow-up must advance startAt AND keep the JQL. Dropping the JQL
        # would page through every issue on the site.
        params = route.calls[1].request.url.params
        assert params["startAt"] == "1"
        assert params["jql"] == "project = ENG"
        assert params["maxResults"] == "1"


@pytest.mark.asyncio
async def test_search_issues_collect_returns_every_page(jira: Jira) -> None:
    """collect() is the agent-facing path; it must span all pages.

    Fails without the wiring: returns 1 issue and looks complete.
    """
    with respx.mock(base_url=f"{_SITE}/rest/api/3") as respx_mock:
        respx_mock.get("/search").mock(
            side_effect=[
                httpx.Response(200, json=_search_page("ENG-1", start_at=0, total=3)),
                httpx.Response(200, json=_search_page("ENG-2", start_at=1, total=3)),
                httpx.Response(200, json=_search_page("ENG-3", start_at=2, total=3)),
            ]
        )

        page1 = await jira.asearch_issues(jql="project = ENG", limit=1)
        assert [i.key for i in await page1.collect()] == ["ENG-1", "ENG-2", "ENG-3"]


@pytest.mark.asyncio
async def test_list_sprints_follows_is_last_and_keeps_state_filter(jira: Jira) -> None:
    """The Agile API signals more with isLast=false; the walk must honour it.

    Fails without the wiring: anext_page() returns None.
    """

    def sprint_page(sprint_id: int, *, start_at: int, is_last: bool) -> dict:
        return {
            "startAt": start_at,
            "maxResults": 1,
            "isLast": is_last,
            "values": [{"id": sprint_id, "name": f"Sprint {sprint_id}", "state": "active"}],
        }

    with respx.mock(base_url=f"{_SITE}/rest/agile/1.0") as respx_mock:
        route = respx_mock.get("/board/7/sprint").mock(
            side_effect=[
                httpx.Response(200, json=sprint_page(101, start_at=0, is_last=False)),
                httpx.Response(200, json=sprint_page(102, start_at=1, is_last=True)),
            ]
        )

        page1 = await jira.alist_sprints(board_id=7, state="active", limit=1)
        assert page1.has_more is True

        page2 = await page1.anext_page()

        assert page2 is not None
        assert [s.id for s in page2.items] == [102]
        assert page2.has_more is False
        params = route.calls[1].request.url.params
        assert params["startAt"] == "1"
        assert params["state"] == "active"


@pytest.mark.asyncio
async def test_search_issues_empty_page_claiming_more_stays_loud(jira: Jira) -> None:
    """An empty page with total > startAt advances nothing — it must raise.

    A fetcher here would re-request startAt=0 forever. The guard leaves it
    unwired on purpose, so anext_page() raises instead of looping or stopping
    quietly.
    """
    with respx.mock(base_url=f"{_SITE}/rest/api/3") as respx_mock:
        respx_mock.get("/search").mock(
            return_value=httpx.Response(
                200, json={"startAt": 0, "maxResults": 50, "total": 5, "issues": []}
            )
        )

        page = await jira.asearch_issues(jql="project = ENG")
        assert page.has_more is True
        assert page.items == []

        with pytest.raises(PaginationNotWiredError):
            await page.anext_page()
