"""Security regression tests for the Salesforce connector's sObject validation.

The connector interpolates the caller-supplied ``sobject`` name into both SOQL
``FROM`` clauses and ``/sobjects/{name}`` REST paths. ``_validate_sobject``
rejects anything outside ``[A-Za-z][A-Za-z0-9_]*`` so a malicious name cannot be
used for SOQL injection or URL-path traversal (hardens bandit B608).
"""

from __future__ import annotations

import pytest
import pytest_asyncio

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
