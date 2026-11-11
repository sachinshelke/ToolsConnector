"""Tests for the Teams connector using respx.

Focus: ``page_url`` origin validation. ``page_url`` is a caller-supplied
absolute URL that is sent through the client carrying the user's
``Authorization: Bearer`` header, so a prompt-injected agent could make
the connector deliver the Microsoft Graph token to any host. Only URLs on
the configured base_url's origin (https) may be followed.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.teams import Teams
from toolsconnector.errors import ValidationError

TOKEN = "fake-graph-token"

# (action name, required kwargs) for every action that accepts page_url.
PAGE_URL_ACTIONS: list[tuple[str, dict[str, Any]]] = [
    ("alist_messages", {"team_id": "t1", "channel_id": "c1"}),
    ("alist_chat_messages", {"chat_id": "chat1"}),
]


@pytest_asyncio.fixture
async def teams() -> Teams:
    connector = Teams(credentials=TOKEN)
    await connector._setup()
    yield connector
    await connector._teardown()


@pytest.mark.asyncio
@pytest.mark.parametrize(("action", "kwargs"), PAGE_URL_ACTIONS)
@pytest.mark.parametrize(
    "page_url",
    [
        "https://attacker.example/x",
        "http://graph.microsoft.com/v1.0/teams/t1/channels/c1/messages",
        "https://graph.microsoft.com@attacker.example/x",
    ],
)
async def test_page_url_actions_reject_foreign_origins(
    teams: Teams, action: str, kwargs: dict[str, Any], page_url: str
) -> None:
    with respx.mock(assert_all_called=False) as mock:
        catch_all = mock.route().mock(return_value=httpx.Response(200, json={"value": []}))
        raised: ValidationError | None = None
        try:
            await getattr(teams, action)(**kwargs, page_url=page_url)
        except ValidationError as exc:
            raised = exc

    leaked = [
        (str(call.request.url), call.request.headers.get("authorization"))
        for call in catch_all.calls
    ]
    assert leaked == [], f"request sent before validation (url, Authorization): {leaked}"
    assert raised is not None, "expected ValidationError for foreign page_url"
    assert raised.connector == "teams"


@pytest.mark.asyncio
async def test_real_graph_next_link_still_pages(teams: Teams) -> None:
    next_link = (
        "https://graph.microsoft.com/v1.0/teams/t1/channels/c1/messages?%24top=50&%24skiptoken=abc"
    )
    with respx.mock(base_url="https://graph.microsoft.com/v1.0") as mock:
        route = mock.get("/teams/t1/channels/c1/messages").mock(
            side_effect=[
                httpx.Response(200, json={"value": [{"id": "m1"}], "@odata.nextLink": next_link}),
                httpx.Response(200, json={"value": [{"id": "m2"}]}),
            ]
        )
        first = await teams.alist_messages(team_id="t1", channel_id="c1")
        assert first.page_state.cursor == next_link

        second = await teams.alist_messages(
            team_id="t1", channel_id="c1", page_url=first.page_state.cursor
        )

    assert [m.id for m in second.items] == ["m2"]
    sent = route.calls.last.request
    assert sent.url == httpx.URL(next_link)
    assert sent.headers["authorization"] == f"Bearer {TOKEN}"
