"""Salesforce connector -- SOQL, SOSL, and sObject CRUD via the Salesforce REST API."""

from __future__ import annotations

from typing import Any, Optional

import httpx

from toolsconnector.connectors._helpers import raise_typed_for_status
from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import (
    ConnectorCategory,
    ProtocolType,
    RateLimitSpec,
)
from toolsconnector.types import PageState, PaginatedList

from ._helpers import (
    parse_describe,
    parse_limits,
    parse_record,
    parse_sobject_info,
)
from .types import (
    SalesforceLimits,
    SalesforceRecord,
    SalesforceRecordId,
    SObjectDescription,
    SObjectInfo,
)


class Salesforce(BaseConnector):
    """Connect to Salesforce to query records, manage sObjects, and run searches.

    Requires an OAuth2 Bearer token passed as ``credentials``.
    The ``base_url`` must point to your Salesforce instance API version
    (e.g., ``https://your-instance.salesforce.com/services/data/v59.0``).

    Supports SOQL queries, SOSL searches, and full sObject CRUD with
    ``nextRecordsUrl``-based pagination for large result sets.
    """

    name = "salesforce"
    display_name = "Salesforce"
    category = ConnectorCategory.CRM
    protocol = ProtocolType.REST
    base_url = "https://your-instance.salesforce.com/services/data/v59.0"
    description = (
        "Connect to Salesforce to run SOQL/SOSL queries, manage "
        "sObject records, and describe object schemas."
    )
    _rate_limit_config = RateLimitSpec(rate=100, period=86400, burst=25)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Initialise the async HTTP client.

        The Salesforce client uses the full ``base_url`` (including the
        API version path) as the base.  Pagination URLs returned by
        Salesforce are absolute paths starting with ``/services/data/``
        so we extract the instance origin for those requests.
        """
        base = self._base_url or self.__class__.base_url
        self._api_base = base.rstrip("/")

        from urllib.parse import urlparse

        parsed = urlparse(self._api_base)
        self._instance_url = f"{parsed.scheme}://{parsed.netloc}"

        self._client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {self._credentials}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=self._timeout,
        )

    async def _teardown(self) -> None:
        """Close the HTTP client."""
        if hasattr(self, "_client"):
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
        absolute: bool = False,
    ) -> dict[str, Any]:
        """Execute an HTTP request against the Salesforce REST API.

        Args:
            method: HTTP method.
            path: API path. If ``absolute`` is False, this is appended to
                ``_api_base``.  If ``absolute`` is True, it is appended to
                the instance origin.
            json: JSON request body.
            params: Query parameters.
            absolute: When True, treat ``path`` as an absolute server path
                (used for ``nextRecordsUrl`` pagination).

        Returns:
            Parsed JSON response dict.

        Raises:
            toolsconnector.errors.APIError (subclass): On any non-2xx response.
                Maps to a typed exception by status: 401 -> InvalidCredentialsError
                or TokenExpiredError; 403 -> PermissionDeniedError; 404 -> NotFoundError;
                409 -> ConflictError; 400/422 -> ValidationError; 429 -> RateLimitError;
                5xx -> ServerError; other 4xx -> APIError. See
                toolsconnector.connectors._helpers.raise_typed_for_status for the full mapping.

        """
        if absolute:
            url = f"{self._instance_url}{path}"
        else:
            url = f"{self._api_base}{path}"

        response = await self._client.request(
            method,
            url,
            json=json,
            params=params,
        )
        raise_typed_for_status(response, connector=self.name)
        if response.status_code == 204:
            return {}
        return response.json()

    # ------------------------------------------------------------------
    # Actions -- Query & Search
    # ------------------------------------------------------------------

    @action("Run a SOQL query")
    async def query(
        self,
        soql: str,
        limit: Optional[int] = None,
    ) -> PaginatedList[SalesforceRecord]:
        """Execute a SOQL query against Salesforce.

        Args:
            soql: SOQL query string (e.g., ``"SELECT Id, Name FROM Account"``).
            limit: Optional LIMIT clause override.

        Returns:
            Paginated list of SalesforceRecord objects.
        """
        query_str = soql
        if limit and "LIMIT" not in soql.upper():
            query_str = f"{soql} LIMIT {limit}"

        params: dict[str, Any] = {"q": query_str}
        data = await self._request("GET", "/query", params=params)

        records = [parse_record(r) for r in data.get("records", [])]
        next_url = data.get("nextRecordsUrl")
        total_size = data.get("totalSize", len(records))
        done = data.get("done", True)

        return PaginatedList(
            items=records,
            page_state=PageState(
                cursor=next_url,
                total_count=total_size,
                has_more=not done and next_url is not None,
            ),
            total_count=total_size,
        )

    @action("Run a SOSL search")
    async def search(self, sosl: str) -> list[SalesforceRecord]:
        """Execute a SOSL search across multiple sObjects.

        Args:
            sosl: SOSL query string.

        Returns:
            List of matching SalesforceRecord objects.
        """
        params: dict[str, Any] = {"q": sosl}
        data = await self._request("GET", "/search", params=params)
        return [parse_record(r) for r in data.get("searchRecords", [])]

    # ------------------------------------------------------------------
    # Actions -- Generic sObject CRUD
    # ------------------------------------------------------------------

    @action("Get a single sObject record")
    async def get_record(
        self,
        sobject: str,
        record_id: str,
    ) -> SalesforceRecord:
        """Retrieve a single sObject record by its ID.

        Args:
            sobject: sObject API name (e.g., ``"Account"``).
            record_id: The Salesforce record ID.

        Returns:
            The requested SalesforceRecord.
        """
        data = await self._request("GET", f"/sobjects/{sobject}/{record_id}")
        return parse_record(data)

    @action("Create a new sObject record", dangerous=True)
    async def create_record(
        self,
        sobject: str,
        fields: dict[str, Any],
    ) -> SalesforceRecordId:
        """Create a new sObject record.

        Args:
            sobject: sObject API name (e.g., ``"Account"``).
            fields: Dict of field API names to values.

        Returns:
            A SalesforceRecordId with the new record's ID.
        """
        data = await self._request("POST", f"/sobjects/{sobject}", json=fields)
        return SalesforceRecordId(
            id=data.get("id", ""),
            success=data.get("success", True),
            errors=data.get("errors", []),
        )

    @action("Update an existing sObject record")
    async def update_record(
        self,
        sobject: str,
        record_id: str,
        fields: dict[str, Any],
    ) -> None:
        """Update fields on an existing sObject record.

        Args:
            sobject: sObject API name (e.g., ``"Account"``).
            record_id: The Salesforce record ID.
            fields: Dict of field API names to new values.
        """
        await self._request("PATCH", f"/sobjects/{sobject}/{record_id}", json=fields)

    @action("Delete an sObject record", dangerous=True)
    async def delete_record(
        self,
        sobject: str,
        record_id: str,
    ) -> None:
        """Delete an sObject record.

        This is a destructive action. The record is moved to the
        Salesforce Recycle Bin.

        Args:
            sobject: sObject API name (e.g., ``"Account"``).
            record_id: The Salesforce record ID to delete.
        """
        await self._request("DELETE", f"/sobjects/{sobject}/{record_id}")

    @action("Upsert a record using an external ID", dangerous=True)
    async def upsert_record(
        self,
        sobject: str,
        external_id_field: str,
        external_id: str,
        fields: dict[str, Any],
    ) -> SalesforceRecordId:
        """Insert or update a record identified by an external ID field.

        Args:
            sobject: sObject API name (e.g., ``"Account"``).
            external_id_field: API name of the external ID field.
            external_id: The external ID value to match on.
            fields: Dict of field API names to values.

        Returns:
            A SalesforceRecordId with the upserted record's ID.
        """
        path = f"/sobjects/{sobject}/{external_id_field}/{external_id}"
        data = await self._request("PATCH", path, json=fields)
        record_id = data.get("id", "")
        return SalesforceRecordId(
            id=record_id,
            success=data.get("success", True),
            errors=data.get("errors", []),
        )

    # ------------------------------------------------------------------
    # Actions -- Schema & metadata
    # ------------------------------------------------------------------

    @action("Describe an sObject schema")
    async def describe_object(self, sobject: str) -> SObjectDescription:
        """Get the full metadata description of an sObject.

        Args:
            sobject: sObject API name (e.g., ``"Account"``).

        Returns:
            An SObjectDescription with full schema details.
        """
        data = await self._request("GET", f"/sobjects/{sobject}/describe")
        return parse_describe(data)

    @action("List all sObjects in the org")
    async def list_objects(self) -> list[SObjectInfo]:
        """List all sObjects available in the Salesforce org.

        Returns:
            List of SObjectInfo with compact metadata for each sObject.
        """
        data = await self._request("GET", "/sobjects")
        return [parse_sobject_info(s) for s in data.get("sobjects", [])]

    @action("Describe all sObjects in the org (global describe)")
    async def describe_global(self) -> list[SObjectInfo]:
        """Return compact metadata for every sObject in the org.

        Returns:
            List of SObjectInfo with compact metadata for each sObject.
        """
        data = await self._request("GET", "/sobjects")
        return [parse_sobject_info(s) for s in data.get("sobjects", [])]

    @action("Get org API usage limits")
    async def get_limits(self) -> SalesforceLimits:
        """Retrieve current API usage limits for the Salesforce org.

        Returns:
            A SalesforceLimits object with usage counters.
        """
        data = await self._request("GET", "/limits")
        return parse_limits(data)

    # ------------------------------------------------------------------
    # Actions -- Typed record creation helpers
    # ------------------------------------------------------------------

    @action("Create a new Lead", dangerous=True)
    async def create_lead(
        self,
        company: str,
        last_name: str,
        email: Optional[str] = None,
        first_name: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> SalesforceRecordId:
        """Create a new Lead record.

        Args:
            company: Company name (required by Salesforce).
            last_name: Contact last name (required by Salesforce).
            email: Email address.
            first_name: Contact first name.
            phone: Phone number.

        Returns:
            A SalesforceRecordId with the new Lead's ID.
        """
        fields: dict[str, Any] = {
            "Company": company,
            "LastName": last_name,
        }
        if email is not None:
            fields["Email"] = email
        if first_name is not None:
            fields["FirstName"] = first_name
        if phone is not None:
            fields["Phone"] = phone

        return await self.create_record("Lead", fields)

    @action("Create a new Contact", dangerous=True)
    async def create_contact(
        self,
        last_name: str,
        account_id: Optional[str] = None,
        email: Optional[str] = None,
        first_name: Optional[str] = None,
    ) -> SalesforceRecordId:
        """Create a new Contact record.

        Args:
            last_name: Contact last name (required by Salesforce).
            account_id: Parent Account ID.
            email: Email address.
            first_name: Contact first name.

        Returns:
            A SalesforceRecordId with the new Contact's ID.
        """
        fields: dict[str, Any] = {"LastName": last_name}
        if account_id is not None:
            fields["AccountId"] = account_id
        if email is not None:
            fields["Email"] = email
        if first_name is not None:
            fields["FirstName"] = first_name

        return await self.create_record("Contact", fields)

    @action("Create a new Opportunity", dangerous=True)
    async def create_opportunity(
        self,
        name: str,
        stage: str,
        close_date: str,
        amount: Optional[float] = None,
        account_id: Optional[str] = None,
    ) -> SalesforceRecordId:
        """Create a new Opportunity record.

        Args:
            name: Opportunity name.
            stage: Sales stage (e.g., ``"Prospecting"``).
            close_date: Expected close date in ``YYYY-MM-DD`` format.
            amount: Monetary amount of the opportunity.
            account_id: Parent Account ID.

        Returns:
            A SalesforceRecordId with the new Opportunity's ID.
        """
        fields: dict[str, Any] = {
            "Name": name,
            "StageName": stage,
            "CloseDate": close_date,
        }
        if amount is not None:
            fields["Amount"] = amount
        if account_id is not None:
            fields["AccountId"] = account_id

        return await self.create_record("Opportunity", fields)

    @action("Create a new Account", dangerous=True)
    async def create_account(
        self,
        name: str,
        industry: Optional[str] = None,
        website: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> SalesforceRecordId:
        """Create a new Account record.

        Args:
            name: Account name.
            industry: Industry classification.
            website: Company website URL.
            phone: Phone number.

        Returns:
            A SalesforceRecordId with the new Account's ID.
        """
        fields: dict[str, Any] = {"Name": name}
        if industry is not None:
            fields["Industry"] = industry
        if website is not None:
            fields["Website"] = website
        if phone is not None:
            fields["Phone"] = phone

        return await self.create_record("Account", fields)

    @action("Create a new Case", dangerous=True)
    async def create_case(
        self,
        subject: str,
        description: Optional[str] = None,
        contact_id: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> SalesforceRecordId:
        """Create a new Case record.

        Args:
            subject: Case subject line.
            description: Detailed case description.
            contact_id: Contact ID to associate with the case.
            priority: Priority level (e.g., ``"High"``, ``"Medium"``).

        Returns:
            A SalesforceRecordId with the new Case's ID.
        """
        fields: dict[str, Any] = {"Subject": subject}
        if description is not None:
            fields["Description"] = description
        if contact_id is not None:
            fields["ContactId"] = contact_id
        if priority is not None:
            fields["Priority"] = priority

        return await self.create_record("Case", fields)

    @action("Create a new Task", dangerous=True)
    async def create_task(
        self,
        subject: str,
        who_id: Optional[str] = None,
        what_id: Optional[str] = None,
        due_date: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> SalesforceRecordId:
        """Create a new Task (activity) record.

        Args:
            subject: Task subject line.
            who_id: Contact or Lead ID (the ``WhoId`` field).
            what_id: Account or Opportunity ID (the ``WhatId`` field).
            due_date: Due date in ``YYYY-MM-DD`` format.
            priority: Priority level (e.g., ``"High"``, ``"Normal"``).

        Returns:
            A SalesforceRecordId with the new Task's ID.
        """
        fields: dict[str, Any] = {"Subject": subject}
        if who_id is not None:
            fields["WhoId"] = who_id
        if what_id is not None:
            fields["WhatId"] = what_id
        if due_date is not None:
            fields["ActivityDate"] = due_date
        if priority is not None:
            fields["Priority"] = priority

        return await self.create_record("Task", fields)

    @action("List recently viewed records for an sObject")
    async def list_recent(
        self,
        sobject: str,
        limit: int = 25,
    ) -> PaginatedList[SalesforceRecord]:
        """List recently viewed records for a given sObject type.

        Args:
            sobject: sObject API name (e.g., ``"Account"``).
            limit: Maximum records to return (max 200).

        Returns:
            Paginated list of recently viewed SalesforceRecord objects.
        """
        capped_limit = min(limit, 200)
        soql = (
            f"SELECT Id, Name, LastViewedDate FROM {sobject} "
            f"WHERE LastViewedDate != null "
            f"ORDER BY LastViewedDate DESC "
            f"LIMIT {capped_limit}"
        )
        return await self.query(soql)

    # ------------------------------------------------------------------
    # Actions -- Events
    # ------------------------------------------------------------------

    @action("Create a new Event", dangerous=True)
    async def create_event(
        self,
        subject: str,
        start: str,
        end: str,
        who_id: Optional[str] = None,
    ) -> SalesforceRecordId:
        """Create a new Event (calendar meeting) record.

        Args:
            subject: Event subject line.
            start: Start datetime in ISO 8601 format.
            end: End datetime in ISO 8601 format.
            who_id: Optional Contact or Lead ID to associate.

        Returns:
            A SalesforceRecordId with the new Event's ID.
        """
        fields: dict[str, Any] = {
            "Subject": subject,
            "StartDateTime": start,
            "EndDateTime": end,
        }
        if who_id is not None:
            fields["WhoId"] = who_id

        return await self.create_record("Event", fields)

    # ------------------------------------------------------------------
    # Actions -- Reports
    # ------------------------------------------------------------------

    @action("List available reports")
    async def list_reports(self) -> list[dict[str, Any]]:
        """List reports available in the Salesforce org.

        Returns:
            List of report summary dicts with Id, Name, and metadata.
        """
        data = await self._request(
            "GET",
            "/analytics/reports",
        )
        return data if isinstance(data, list) else []

    @action("Run a Salesforce report")
    async def run_report(self, report_id: str) -> dict[str, Any]:
        """Execute a Salesforce report and return the results.

        Args:
            report_id: The 15/18-character report ID.

        Returns:
            Dict containing report metadata and tabular results.
        """
        data = await self._request(
            "POST",
            f"/analytics/reports/{report_id}",
        )
        return data
