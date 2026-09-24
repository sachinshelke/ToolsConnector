"""Tests for the Docker Hub connector using respx.

Focus: ``page`` cursor origin validation. ``page`` is a caller-supplied
absolute URL that is sent through the client carrying the user's
``Authorization: Bearer`` header, so a prompt-injected agent could make
the connector deliver the Docker Hub token to any host. Only URLs on the
configured base_url's origin (https) may be followed.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.dockerhub import DockerHub
from toolsconnector.errors import ValidationError

TOKEN = "dckr_pat_fake"

# (action name, required kwargs) for every action that accepts page.
PAGE_ACTIONS: list[tuple[str, dict[str, Any]]] = [
    ("asearch_repos", {"query": "nginx"}),
    ("alist_repos", {"namespace": "library"}),
    ("alist_tags", {"namespace": "library", "repo": "nginx"}),
]


@pytest_asyncio.fixture
async def dockerhub() -> DockerHub:
    # A credential without ":" is used as the bearer token directly (no login).
    connector = DockerHub(credentials=TOKEN)
    await connector._setup()
    yield connector
    await connector._teardown()


@pytest.mark.asyncio
@pytest.mark.parametrize(("action", "kwargs"), PAGE_ACTIONS)
@pytest.mark.parametrize(
    "page",
    [
        "https://attacker.example/x",
        "http://hub.docker.com/v2/repositories/library/?page=2",
        "https://hub.docker.com@attacker.example/x",
        "https://hub.docker.com.attacker.example/v2/repositories/library/",
    ],
)
async def test_page_actions_reject_foreign_origins(
    dockerhub: DockerHub, action: str, kwargs: dict[str, Any], page: str
) -> None:
    with respx.mock(assert_all_called=False) as mock:
        catch_all = mock.route().mock(return_value=httpx.Response(200, json={"results": []}))
        raised: Exception | None = None
        try:
            await getattr(dockerhub, action)(**kwargs, page=page)
        except Exception as exc:  # recorded; the leak check below runs first
            raised = exc

    leaked = [
        (str(call.request.url), call.request.headers.get("authorization"))
        for call in catch_all.calls
    ]
    assert leaked == [], f"request sent before validation (url, Authorization): {leaked}"
    assert isinstance(raised, ValidationError), f"expected ValidationError, got {raised!r}"
    assert raised.connector == "dockerhub"


@pytest.mark.asyncio
async def test_real_next_url_still_pages(dockerhub: DockerHub) -> None:
    # Shape of a live hub.docker.com `next` value.
    next_url = "https://hub.docker.com/v2/repositories/library/?page=2&page_size=2"
    with respx.mock(base_url="https://hub.docker.com/v2") as mock:
        route = mock.get("/repositories/library/").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={"count": 3, "next": next_url, "results": [{"name": "a"}, {"name": "b"}]},
                ),
                httpx.Response(200, json={"count": 3, "next": None, "results": [{"name": "c"}]}),
            ]
        )
        first = await dockerhub.alist_repos(namespace="library", limit=2)
        assert first.page_state.cursor == next_url

        second = await dockerhub.alist_repos(namespace="library", page=first.page_state.cursor)

    assert [r.name for r in second.items] == ["c"]
    assert second.page_state.has_more is False
    sent = route.calls.last.request
    assert sent.url == httpx.URL(next_url)
    assert sent.headers["authorization"] == f"Bearer {TOKEN}"
