"""Security regression tests for the Salesforce connector's sObject validation.

The connector interpolates the caller-supplied ``sobject`` name into both SOQL
``FROM`` clauses and ``/sobjects/{name}`` REST paths. ``_validate_sobject``
rejects anything outside ``[A-Za-z][A-Za-z0-9_]*`` so a malicious name cannot be
used for SOQL injection or URL-path traversal (hardens bandit B608).
"""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.salesforce import Salesforce
from toolsconnector.connectors.salesforce.connector import _validate_sobject


@pytest.mark.parametrize(
    "name",
    [
        "Account",
        "Contact",
        "Opportunity",
        "My_Custom_Object__c",  # custom object
        "ns__My_Object__c",  # namespaced custom object
        "A1",
    ],
)
def test_validate_sobject_accepts_valid_api_names(name: str) -> None:
    assert _validate_sobject(name) == name


@pytest.mark.parametrize(
    "name",
    [
        "",  # empty
        "1Account",  # must start with a letter
        "Account; DROP TABLE Foo",  # command/SOQL injection
        "Account WHERE Id != null",  # SOQL clause injection
        "Account'--",  # quote / comment injection
        "Account OR 1=1",  # logic injection
        "../../etc/passwd",  # path traversal
        "Account/describe",  # path-segment injection
        "Account Name",  # whitespace
        "Acc(ount)",  # parentheses
        "Café",  # non-ASCII (regex is ASCII-only by design)
        "Account\n",  # trailing newline must not slip past the anchor
    ],
)
def test_validate_sobject_rejects_injection_attempts(name: str) -> None:
    with pytest.raises(ValueError, match="Invalid sObject name"):
        _validate_sobject(name)


@pytest_asyncio.fixture
async def salesforce() -> Salesforce:
    connector = Salesforce(credentials="fake-bearer-token")
    await connector._setup()
    yield connector
    await connector._teardown()


@pytest.mark.asyncio
async def test_get_record_rejects_malicious_sobject_before_request(
    salesforce: Salesforce,
) -> None:
    """The guard fires while building the path — before any HTTP call.

    No network is mocked here, so reaching the transport would raise a
    different (connection) error; a ``ValueError`` proves validation ran first.
    """
    with pytest.raises(ValueError, match="Invalid sObject name"):
        await salesforce.get_record(sobject="Account; DROP TABLE", record_id="001")


@pytest.mark.asyncio
async def test_list_recent_rejects_soql_injection(salesforce: Salesforce) -> None:
    with pytest.raises(ValueError, match="Invalid sObject name"):
        await salesforce.list_recent(sobject="Account WHERE 1=1")


# ---------------------------------------------------------------------------
# Composite actions must await the async entry point of the action they wrap.
# BaseConnector installs each action's SYNC wrapper under its bare name on the
# instance, so ``await self.create_record(...)`` ran the POST on a worker thread
# and then raised ``TypeError: object SalesforceRecordId can't be used in
# 'await' expression`` — the record was created but the caller saw an error.
# ---------------------------------------------------------------------------

_SF_BASE = "https://your-instance.salesforce.com/services/data/v59.0"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "kwargs", "sobject"),
    [
        ("acreate_lead", {"company": "Acme", "last_name": "Doe"}, "Lead"),
        ("acreate_contact", {"last_name": "Doe"}, "Contact"),
        (
            "acreate_opportunity",
            {"name": "Deal", "stage": "Prospecting", "close_date": "2026-12-31"},
            "Opportunity",
        ),
        ("acreate_account", {"name": "Acme"}, "Account"),
        ("acreate_case", {"subject": "Broken"}, "Case"),
        ("acreate_task", {"subject": "Call back"}, "Task"),
        (
            "acreate_event",
            {"subject": "Sync", "start": "2026-10-01T10:00:00Z", "end": "2026-10-01T11:00:00Z"},
            "Event",
        ),
    ],
)
async def test_create_wrappers_post_exactly_once(
    salesforce: Salesforce, action: str, kwargs: dict, sobject: str
) -> None:
    with respx.mock(base_url=_SF_BASE, assert_all_called=True) as respx_mock:
        route = respx_mock.post(f"/sobjects/{sobject}").mock(
            return_value=httpx.Response(201, json={"id": "001X", "success": True, "errors": []})
        )

        result = await getattr(salesforce, action)(**kwargs)

    assert route.call_count == 1
    assert result.id == "001X"
    assert result.success is True


@pytest.mark.asyncio
async def test_list_recent_returns_records_from_one_query(salesforce: Salesforce) -> None:
    with respx.mock(base_url=_SF_BASE, assert_all_called=True) as respx_mock:
        route = respx_mock.get("/query").mock(
            return_value=httpx.Response(
                200,
                json={
                    "totalSize": 1,
                    "done": True,
                    "records": [{"attributes": {"type": "Account"}, "Id": "001A", "Name": "Acme"}],
                },
            )
        )

        result = await salesforce.alist_recent(sobject="Account", limit=5)

    assert route.call_count == 1
    assert "FROM Account" in route.calls[0].request.url.params["q"]
    assert len(result.items) == 1
