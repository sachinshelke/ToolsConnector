"""Regression tests: X composite write actions must await create_tweet's async entry point.

``BaseConnector`` installs each action's SYNC wrapper under its bare name on the
instance, so ``await self.create_tweet(...)`` inside an action posted the tweet
on a worker thread and then raised ``TypeError: object Tweet can't be used in
'await' expression`` — the tweet went live but the caller saw an error, and a
retry would post it twice.
"""

from __future__ import annotations

import json

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.x import X


@pytest_asyncio.fixture
async def x() -> X:
    connector = X(credentials="fake-user-context-token")
    await connector._setup()
    yield connector
    await connector._teardown()


@pytest.mark.asyncio
async def test_reply_to_tweet_posts_exactly_once(x: X) -> None:
    with respx.mock(base_url="https://api.x.com/2", assert_all_called=True) as respx_mock:
        route = respx_mock.post("/tweets").mock(
            return_value=httpx.Response(201, json={"data": {"id": "t2", "text": "hi"}})
        )

        tweet = await x.areply_to_tweet(tweet_id="t1", text="hi")

    assert route.call_count == 1
    assert json.loads(route.calls[0].request.read()) == {
        "text": "hi",
        "reply": {"in_reply_to_tweet_id": "t1"},
    }
    assert tweet.id == "t2"


@pytest.mark.asyncio
async def test_create_thread_posts_each_tweet_once_chained_as_replies(x: X) -> None:
    with respx.mock(base_url="https://api.x.com/2", assert_all_called=True) as respx_mock:
        route = respx_mock.post("/tweets").mock(
            side_effect=[
                httpx.Response(201, json={"data": {"id": "t1", "text": "one"}}),
                httpx.Response(201, json={"data": {"id": "t2", "text": "two"}}),
            ]
        )

        thread = await x.acreate_thread(["one", "two"])

    assert route.call_count == 2
    bodies = [json.loads(c.request.read()) for c in route.calls]
    assert bodies == [
        {"text": "one"},
        {"text": "two", "reply": {"in_reply_to_tweet_id": "t1"}},
    ]
    assert [t.id for t in thread] == ["t1", "t2"]
