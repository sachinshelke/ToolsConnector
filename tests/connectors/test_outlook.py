"""Tests for the Outlook connector using respx.

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

from toolsconnector.connectors.outlook import Outlook
from toolsconnector.errors import ValidationError

TOKEN = "fake-graph-token"

# (action name, required kwargs) for every action that accepts page_url.
PAGE_URL_ACTIONS: list[tuple[str, dict[str, Any]]] = [
    ("alist_messages", {}),
    ("asearch_messages", {"query": "invoice"}),
    ("alist_contacts", {}),
    ("alist_calendar_events", {}),
]

FOREIGN_PAGE_URLS = [
    "https://attacker.example/x",
    # Plaintext downgrade on the right host.
    "http://graph.microsoft.com/v1.0/me/messages?$skip=25",
    # Suffix/prefix look-alikes.
    "https://graph.microsoft.com.attacker.example/v1.0/me/messages",
    "https://evilgraph.microsoft.com/v1.0/me/messages",
    # Userinfo trick: the real host is attacker.example.
    "https://graph.microsoft.com@attacker.example/v1.0/me/messages",
    # Right host, wrong port.
    "https://graph.microsoft.com:8443/v1.0/me/messages",
    # Scheme-relative and relative forms are not nextLinks.
    "//attacker.example/x",
    "/me/messages",
]


@pytest_asyncio.fixture
async def outlook() -> Outlook:
    connector = Outlook(credentials=TOKEN)
    await connector._setup()
    yield connector
    await connector._teardown()


async def _assert_blocked(connector: Outlook, action: str, kwargs: dict[str, Any]) -> None:
    """Call ``action`` and assert it raised before any request was sent."""
    with respx.mock(assert_all_called=False) as mock:
        catch_all = mock.route().mock(return_value=httpx.Response(200, json={"value": []}))
        raised: ValidationError | None = None
        try:
            await getattr(connector, action)(**kwargs)
        except ValidationError as exc:
            raised = exc

    leaked = [
        (str(call.request.url), call.request.headers.get("authorization"))
        for call in catch_all.calls
    ]
    assert leaked == [], f"request sent before validation (url, Authorization): {leaked}"
    assert raised is not None, "expected ValidationError for foreign page_url"
    assert raised.connector == "outlook"


@pytest.mark.asyncio
async def test_list_messages_rejects_attacker_page_url(outlook: Outlook) -> None:
    await _assert_blocked(outlook, "alist_messages", {"page_url": "https://attacker.example/x"})


@pytest.mark.asyncio
@pytest.mark.parametrize("page_url", FOREIGN_PAGE_URLS)
async def test_list_messages_rejects_foreign_origins(outlook: Outlook, page_url: str) -> None:
    await _assert_blocked(outlook, "alist_messages", {"page_url": page_url})


@pytest.mark.asyncio
@pytest.mark.parametrize(("action", "kwargs"), PAGE_URL_ACTIONS)
async def test_every_page_url_action_rejects_attacker(
    outlook: Outlook, action: str, kwargs: dict[str, Any]
) -> None:
    await _assert_blocked(outlook, action, {**kwargs, "page_url": "https://attacker.example/x"})


@pytest.mark.asyncio
async def test_real_graph_next_link_still_pages(outlook: Outlook) -> None:
    next_link = "https://graph.microsoft.com/v1.0/me/messages?%24skip=25&%24top=25"
    with respx.mock(base_url="https://graph.microsoft.com/v1.0") as mock:
        route = mock.get("/me/messages").mock(
            side_effect=[
                httpx.Response(200, json={"value": [{"id": "m1"}], "@odata.nextLink": next_link}),
                httpx.Response(200, json={"value": [{"id": "m2"}]}),
            ]
        )
        first = await outlook.alist_messages(limit=25)
        assert first.page_state.cursor == next_link

        second = await outlook.alist_messages(page_url=first.page_state.cursor)

    assert [m.id for m in second.items] == ["m2"]
    assert second.page_state.has_more is False
    sent = route.calls.last.request
    assert sent.url == httpx.URL(next_link)
    assert sent.headers["authorization"] == f"Bearer {TOKEN}"


@pytest.mark.asyncio
async def test_national_cloud_base_url_host_is_the_allowed_one() -> None:
    connector = Outlook(credentials=TOKEN, base_url="https://graph.microsoft.us/v1.0")
    await connector._setup()
    try:
        next_link = "https://graph.microsoft.us/v1.0/me/messages?%24skip=25"
        with respx.mock(base_url="https://graph.microsoft.us/v1.0") as mock:
            mock.get("/me/messages").mock(
                return_value=httpx.Response(200, json={"value": [{"id": "gov1"}]})
            )
            page = await connector.alist_messages(page_url=next_link)
        assert [m.id for m in page.items] == ["gov1"]

        # The commercial-cloud host is not the configured one, so it is refused.
        await _assert_blocked(
            connector,
            "alist_messages",
            {"page_url": "https://graph.microsoft.com/v1.0/me/messages"},
        )
    finally:
        await connector._teardown()
