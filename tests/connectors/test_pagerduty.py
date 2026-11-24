"""Regression test: acknowledge_incident must await update_incident's async entry point.

``BaseConnector`` installs each action's SYNC wrapper under its bare name on the
instance, so ``await self.update_incident(...)`` inside acknowledge_incident sent
the PUT on a worker thread and then raised ``TypeError: object PDIncident can't
be used in 'await' expression`` — the incident was acknowledged but the caller
saw an error.
"""

from __future__ import annotations

import json

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.pagerduty import PagerDuty


@pytest_asyncio.fixture
async def pagerduty() -> PagerDuty:
    connector = PagerDuty(credentials="fake-api-key")
    await connector._setup()
    yield connector
    await connector._teardown()


@pytest.mark.asyncio
async def test_acknowledge_incident_puts_exactly_once(pagerduty: PagerDuty) -> None:
    with respx.mock(base_url="https://api.pagerduty.com", assert_all_called=True) as respx_mock:
        route = respx_mock.put("/incidents/PINC1").mock(
            return_value=httpx.Response(
                200, json={"incident": {"id": "PINC1", "status": "acknowledged"}}
            )
        )

        incident = await pagerduty.aacknowledge_incident(incident_id="PINC1")

    assert route.call_count == 1
    assert json.loads(route.calls[0].request.read()) == {
        "incident": {"type": "incident_reference", "status": "acknowledged"}
    }
    assert incident.id == "PINC1"
    assert incident.status == "acknowledged"
