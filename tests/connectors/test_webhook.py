"""Regression tests: webhook composite actions must await send_webhook's async entry point.

``BaseConnector`` installs each action's SYNC wrapper under its bare name on the
instance, so ``await self.send_webhook(...)`` inside an action ran the POST on a
worker thread and then raised ``TypeError: object WebhookResponse can't be used
in 'await' expression`` — the write landed but the caller saw an error.
"""

from __future__ import annotations

import json

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.webhook import Webhook

URL = "https://hooks.example.test/in"


@pytest_asyncio.fixture
async def webhook() -> Webhook:
    connector = Webhook()
    await connector._setup()
    yield connector
    await connector._teardown()


@pytest.mark.asyncio
async def test_send_batch_posts_each_payload_exactly_once(webhook: Webhook) -> None:
    with respx.mock(assert_all_called=True) as respx_mock:
        route = respx_mock.post(URL).mock(return_value=httpx.Response(200, json={"ok": True}))

        result = await webhook.asend_batch(URL, [{"n": 1}, {"n": 2}])

    assert route.call_count == 2
    assert [json.loads(c.request.read()) for c in route.calls] == [{"n": 1}, {"n": 2}]
    assert (result.total, result.succeeded, result.failed) == (2, 2, 0)


@pytest.mark.asyncio
async def test_send_with_retry_posts_once_on_first_success(webhook: Webhook) -> None:
    with respx.mock(assert_all_called=True) as respx_mock:
        route = respx_mock.post(URL).mock(return_value=httpx.Response(200, json={"ok": True}))

        result = await webhook.asend_with_retry(URL, {"n": 1}, max_retries=3, delay=0)

    assert route.call_count == 1
    assert result.success is True
    assert result.status_code == 200
