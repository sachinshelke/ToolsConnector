"""Regression test: cancel_event must await get_event's async entry point.

``BaseConnector`` installs each action's SYNC wrapper under its bare name on the
instance, so ``await self.get_event(...)`` inside cancel_event re-fetched the
event on a worker thread and then raised ``TypeError: object CalendlyEvent can't
be used in 'await' expression`` — the event was already cancelled but the caller
saw an error.
"""

from __future__ import annotations

import json

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.calendly import Calendly


@pytest_asyncio.fixture
async def calendly() -> Calendly:
    connector = Calendly(credentials="fake-personal-access-token")
    await connector._setup()
    yield connector
    await connector._teardown()


@pytest.mark.asyncio
async def test_cancel_event_cancels_once_then_returns_refetched_event(calendly: Calendly) -> None:
    uri = "https://api.calendly.com/scheduled_events/ev-1"
    with respx.mock(base_url="https://api.calendly.com", assert_all_called=True) as respx_mock:
        cancel = respx_mock.post("/scheduled_events/ev-1/cancellation").mock(
            return_value=httpx.Response(201, json={"resource": {"reason": "conflict"}})
        )
        refetch = respx_mock.get("/scheduled_events/ev-1").mock(
            return_value=httpx.Response(
                200, json={"resource": {"uri": uri, "name": "Intro", "status": "canceled"}}
            )
        )

        event = await calendly.acancel_event(event_uuid="ev-1", reason="conflict")

    assert cancel.call_count == 1
    assert json.loads(cancel.calls[0].request.read()) == {"reason": "conflict"}
    assert refetch.call_count == 1
    assert event.uri == uri
    assert event.status == "canceled"
