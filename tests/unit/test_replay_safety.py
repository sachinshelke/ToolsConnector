"""A write whose outcome is unknown must not be sent twice."""

from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from toolsconnector.errors import ServerError
from toolsconnector.errors import TimeoutError as TCTimeoutError
from toolsconnector.serve import ToolKit

ISSUES = "https://api.github.com/repos/o/r/issues"


def _kit() -> ToolKit:
    return ToolKit(["github"], credentials={"github": "x"}, action_timeout=1.5, timeout_budget=6.0)


async def _create() -> None:
    await _kit().aexecute("github_create_issue", {"owner": "o", "repo": "r", "title": "t"})


@pytest.mark.asyncio
async def test_write_is_not_resent_after_a_timeout() -> None:
    # respx does not record a call that is cancelled mid-flight, so count here.
    sent: list[str] = []

    async def hang(request: httpx.Request) -> httpx.Response:
        sent.append(str(request.url))
        await asyncio.sleep(30)
        return httpx.Response(200)

    with respx.mock(assert_all_called=False) as mock:
        mock.post(ISSUES).mock(side_effect=hang)
        with pytest.raises(TCTimeoutError) as err:
            await _create()
    assert sent == [ISSUES]
    assert err.value.retry_eligible is False
    assert "already have taken effect" in (err.value.suggestion or "")


@pytest.mark.asyncio
async def test_write_is_not_resent_after_a_5xx() -> None:
    with respx.mock() as mock:
        route = mock.post(ISSUES).mock(return_value=httpx.Response(503))
        with pytest.raises(ServerError) as err:
            await _create()
    assert route.call_count == 1
    assert err.value.retry_eligible is False


@pytest.mark.asyncio
async def test_rate_limited_write_is_retried_because_it_was_refused() -> None:
    with respx.mock() as mock:
        route = mock.post(ISSUES).mock(
            side_effect=[
                httpx.Response(429, headers={"retry-after": "0"}),
                httpx.Response(201, json={"id": 1, "number": 1, "title": "t", "state": "open"}),
            ]
        )
        await _create()
    assert route.call_count == 2


@pytest.mark.asyncio
async def test_declared_read_is_still_retried() -> None:
    with respx.mock() as mock:
        route = mock.get(ISSUES).mock(
            side_effect=[httpx.Response(503), httpx.Response(200, json=[])]
        )
        kit = _kit()
        await kit.aexecute("github_list_issues", {"owner": "o", "repo": "r"})
    assert route.call_count == 2


@pytest.mark.asyncio
async def test_failed_writes_still_open_the_circuit() -> None:
    kit = ToolKit(["github"], credentials={"github": "x"}, circuit_breaker_threshold=2)
    with respx.mock() as mock:
        route = mock.post(ISSUES).mock(return_value=httpx.Response(503))
        for _ in range(3):
            with pytest.raises(ServerError):
                await kit.aexecute("github_create_issue", {"owner": "o", "repo": "r", "title": "t"})
    assert route.call_count == 2
