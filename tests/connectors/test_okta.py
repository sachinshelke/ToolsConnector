"""Pagination tests for the Okta connector using respx.

Okta pages through the ``Link`` response header. ``rel="next"`` points at an
absolute URL carrying the original query plus an opaque ``after`` token. The
connector used to store that whole URL as ``page_state.cursor``, but none of the
list actions accepted a cursor and nothing was wired, so page two was
unreachable by any route.

These tests pin that each list action accepts ``after``, reports the ``after``
token as ``page_state.cursor`` (keeping the full URL in ``extra``), and walks
pages itself through ``anext_page()`` / ``collect()``.
"""

from __future__ import annotations

from typing import Optional

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.okta import Okta

_API = "https://acme.okta.com/api/v1"


@pytest_asyncio.fixture
async def okta() -> Okta:
    """Okta connector for the fake ``acme`` org."""
    connector = Okta(credentials="fake-ssws-token:acme")
    await connector._setup()
    yield connector
    await connector._teardown()


def _resp(items: list[dict], *, next_url: Optional[str]) -> httpx.Response:
    """An Okta list response: a bare JSON array plus a Link header."""
    links = [f'<{_API}/current>; rel="self"']
    if next_url:
        links.append(f'<{next_url}>; rel="next"')
    return httpx.Response(200, json=items, headers={"link": ", ".join(links)})


def _user(user_id: str) -> dict:
    return {"id": user_id, "status": "ACTIVE", "profile": {"login": f"{user_id}@acme.test"}}


@pytest.mark.asyncio
async def test_list_users_anext_page_fetches_page_two(okta: Okta) -> None:
    """anext_page() must return page two, not None, with the search kept.

    Fails on the old code: page_state.cursor was the full URL and nothing was
    wired, so anext_page() returned None while has_more was True.
    """
    next_url = f"{_API}/users?limit=1&search=status+eq+%22ACTIVE%22&after=00u2"
    with respx.mock(base_url=_API) as respx_mock:
        route = respx_mock.get("/users").mock(
            side_effect=[
                _resp([_user("00u1")], next_url=next_url),
                _resp([_user("00u2")], next_url=None),
            ]
        )

        page1 = await okta.alist_users(search='status eq "ACTIVE"', limit=1)
        assert page1.has_more is True
        assert page1.page_state.cursor == "00u2"
        assert page1.page_state.extra["next_url"] == next_url

        page2 = await page1.anext_page()

        assert page2 is not None, "anext_page() returned None despite has_more=True"
        assert [u.id for u in page2.items] == ["00u2"]
        assert page2.has_more is False
        assert await page2.anext_page() is None

        # Dropping the search would page through every user in the org.
        params = route.calls[1].request.url.params
        assert params["after"] == "00u2"
        assert params["search"] == 'status eq "ACTIVE"'
        assert params["limit"] == "1"


@pytest.mark.asyncio
async def test_list_groups_collect_returns_every_page(okta: Okta) -> None:
    """collect() is the agent-facing path; it must span all pages.

    Fails without the wiring: returns 1 group and looks complete.
    """

    def group(gid: str) -> dict:
        return {"id": gid, "type": "OKTA_GROUP", "profile": {"name": gid}}

    with respx.mock(base_url=_API) as respx_mock:
        respx_mock.get("/groups").mock(
            side_effect=[
                _resp([group("g1")], next_url=f"{_API}/groups?limit=1&after=g1"),
                _resp([group("g2")], next_url=None),
            ]
        )

        page1 = await okta.alist_groups(limit=1)
        assert [g.id for g in await page1.collect()] == ["g1", "g2"]


@pytest.mark.asyncio
async def test_list_group_members_accepts_after_for_manual_paging(okta: Okta) -> None:
    """Callers paging by hand must be able to pass the cursor back directly.

    Fails on the old code: `after` was not a parameter.
    """
    with respx.mock(base_url=_API) as respx_mock:
        route = respx_mock.get("/groups/g1/users").mock(
            return_value=_resp([_user("00u9")], next_url=None)
        )

        page = await okta.alist_group_members(group_id="g1", after="00u8")

        assert [u.id for u in page.items] == ["00u9"]
        assert route.calls[0].request.url.params["after"] == "00u8"


@pytest.mark.asyncio
async def test_list_system_logs_polling_collect_terminates(okta: Okta) -> None:
    """System Log polling always returns a next link, even when caught up.

    Without `until`, Okta keeps sending rel="next". collect() must still stop
    once a page comes back empty, instead of polling forever, and it must return
    everything fetched up to that point.
    """

    def event(uuid: str) -> dict:
        return {"uuid": uuid, "eventType": "user.session.start"}

    with respx.mock(base_url=_API) as respx_mock:
        route = respx_mock.get("/logs").mock(
            side_effect=[
                _resp([event("e1")], next_url=f"{_API}/logs?limit=1&since=S&after=a2"),
                _resp([event("e2")], next_url=f"{_API}/logs?limit=1&since=S&after=a3"),
                _resp([], next_url=f"{_API}/logs?limit=1&since=S&after=a3"),
            ]
        )

        page1 = await okta.alist_system_logs(since="S", limit=1)
        collected = await page1.collect()

        assert [e.uuid for e in collected] == ["e1", "e2"]
        assert route.call_count == 3
        assert route.calls[2].request.url.params["since"] == "S"
