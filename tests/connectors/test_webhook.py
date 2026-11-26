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
from toolsconnector.errors import ValidationError

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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://localhost:9/",
        "http://10.0.0.5/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://0.0.0.0/",
        "http://100.64.0.1/",
        "http://[64:ff9b::a9fe:a9fe]/",
        "http://[::127.0.0.1]/",
        "http://[::]/",
    ],
)
async def test_non_public_destinations_are_refused(webhook: Webhook, url: str) -> None:
    with respx.mock(assert_all_called=False) as respx_mock:
        route = respx_mock.route().mock(return_value=httpx.Response(200))
        with pytest.raises(ValidationError, match="non-public"):
            await webhook.asend_json(url, {"n": 1})
    assert route.call_count == 0


@pytest.mark.asyncio
async def test_private_destination_can_be_allowed(
    webhook: Webhook, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TC_WEBHOOK_ALLOW_PRIVATE", "1")
    with respx.mock() as respx_mock:
        respx_mock.post("http://127.0.0.1/").mock(return_value=httpx.Response(200))
        result = await webhook.asend_json("http://127.0.0.1/", {"n": 1})
    assert result.success


@pytest.mark.asyncio
async def test_redirect_does_not_carry_the_key_to_another_host(webhook: Webhook) -> None:
    with respx.mock(assert_all_called=False) as respx_mock:
        respx_mock.post(URL).mock(
            return_value=httpx.Response(307, headers={"location": "https://evil.example.test/"})
        )
        evil = respx_mock.post("https://evil.example.test/").mock(return_value=httpx.Response(200))
        result = await webhook.asend_with_api_key(URL, {"n": 1}, api_key="SECRET")
    assert evil.call_count == 0
    assert result.status_code == 307 and result.success is False
