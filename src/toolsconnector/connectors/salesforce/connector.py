"""Salesforce connector -- SOQL, SOSL, and sObject CRUD via the Salesforce REST API."""

from __future__ import annotations

from typing import Any, Optional

import httpx

from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import (
    ConnectorCategory,
    ProtocolType,
    RateLimitSpec,
)
from toolsconnector.types import PageState, PaginatedList

from .types import (
    SalesforceRecord,
    SalesforceRecordId,
    SObjectDescription,
    SObjectFieldInfo,
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

        # Extract instance origin (e.g. https://your-instance.salesforce.com)
        # for absolute nextRecordsUrl pagination paths.
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
            httpx.HTTPStatusError: On non-2xx responses.
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
        response.raise_for_status()
        if response.status_code == 204:
            return {}
        return response.json()

    # ------------------------------------------------------------------
    # Response parsers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_record(data: dict[str, Any]) -> SalesforceRecord:
        """Parse a raw Salesforce record JSON into a SalesforceRecord.

        Salesforce returns records as flat dicts with an ``attributes``
        key containing metadata.  We separate ``attributes`` and ``Id``
        from the remaining fields.

        Args:
            data: Raw JSON dict for a single record.

        Returns:
            A SalesforceRecord instance.
        """
        attributes = data.get("attributes", {})
        record_id = data.get("Id") or data.get("id")
        fields = {
            k: v
            for k, v in data.items()
            if k not in ("attributes", "Id", "id")
        }
        return SalesforceRecord(
            id=record_id,
            attributes=attributes,
            fields=fields,
        )

    @staticmethod
    def _parse_sobject_info(data: dict[str, Any]) -> SObjectInfo:
        """Parse a compact sObject description from the global describe."""
        return SObjectInfo(
            name=data.get("name", ""),
            label=data.get("label", ""),
            label_plural=data.get("labelPlural"),
            key_prefix=data.get("keyPrefix"),
            queryable=data.get("queryable", False),
            searchable=data.get("searchable", False),
            createable=data.get("createable", False),
            updateable=data.get("updateable", False),
            deletable=data.get("deletable", False),
            custom=data.get("custom", False),
            urls=data.get("urls", {}),
        )

    @staticmethod
    def _parse_field_info(data: dict[str, Any]) -> SObjectFieldInfo:
        """Parse a single field description."""
        return SObjectFieldInfo(
            name=data.get("name", ""),
            label=data.get("label", ""),
            type=data.get("type", ""),
            length=data.get("length"),
            nillable=data.get("nillable", False),
            updateable=data.get("updateable", False),
            createable=data.get("createable", False),
            custom=data.get("custom", False),
        )

    @classmethod
    def _parse_describe(cls, data: dict[str, Any]) -> SObjectDescription:
        """Parse a full sObject describe response."""
        fields = [
            cls._parse_field_info(f) for f in data.get("fields", [])
        ]
        return SObjectDescription(
            name=data.get("name", ""),
            label=data.get("label", ""),
            label_plural=data.get("labelPlural"),
            key_prefix=data.get("keyPrefix"),
            queryable=data.get("queryable", False),
            searchable=data.get("searchable", False),
            createable=data.get("createable", False),
            updateable=data.get("updateable", False),
            deletable=data.get("deletable", False),
            custom=data.get("custom", False),
            fields=fields,
            record_type_infos=data.get("recordTypeInfos", []),
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    @action("Run a SOQL query")
    async def query(
        self,
        soql: str,
        limit: Optional[int] = None,
    ) -> PaginatedList[SalesforceRecord]:
        """Execute a SOQL query against Salesforce.

        Large result sets are paginated via ``nextRecordsUrl``.  Use
        ``PaginatedList.anext_page()`` or ``collect()`` to iterate.

        Args:
            soql: SOQL query string (e.g., ``"SELECT Id, Name FROM Account"``).
            limit: Optional LIMIT clause override.  If provided and the
                query does not already contain a LIMIT, one is appended.

        Returns:
            Paginated list of SalesforceRecord objects.
        """
        query_str = soql
        if limit and "LIMIT" not in soql.upper():
            query_str = f"{soql} LIMIT {limit}"

        params: dict[str, Any] = {"q": query_str}
        data = await self._request("GET", "/query", params=params)

        records = [self._parse_record(r) for r in data.get("records", [])]
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

    @action("Get a single sObject record")
    async def get_record(
        self,
        sobject: str,
        record_id: str,
    ) -> SalesforceRecord:
        """Retrieve a single sObject record by its ID.

        Args:
            sobject: sObject API name (e.g., ``"Account"``, ``"Contact"``).
            record_id: The Salesforce 15- or 18-character record ID.

        Returns:
            The requested SalesforceRecord.
        """
        data = await self._request(
            "GET", f"/sobjects/{sobject}/{record_id}"
        )
        return self._parse_record(data)

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
        data = await self._request(
            "POST", f"/sobjects/{sobject}", json=fields
        )
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
        await self._request(
            "PATCH", f"/sobjects/{sobject}/{record_id}", json=fields
        )

    @action("Delete an sObject record", dangerous=True)
    async def delete_record(
        self,
        sobject: str,
        record_id: str,
    ) -> None:
        """Delete an sObject record.

        This is a destructive action. The record is moved to the
        Salesforce Recycle Bin but can be permanently lost if the
        bin is emptied.

        Args:
            sobject: sObject API name (e.g., ``"Account"``).
            record_id: The Salesforce record ID to delete.
        """
        await self._request(
            "DELETE", f"/sobjects/{sobject}/{record_id}"
        )

    @action("Describe an sObject schema")
    async def describe_object(self, sobject: str) -> SObjectDescription:
        """Get the full metadata description of an sObject.

        Returns field definitions, record type information, and
        object-level capabilities (queryable, createable, etc.).

        Args:
            sobject: sObject API name (e.g., ``"Account"``).

        Returns:
            An SObjectDescription with full schema details.
        """
        data = await self._request("GET", f"/sobjects/{sobject}/describe")
        return self._parse_describe(data)

    @action("List all sObjects in the org")
    async def list_objects(self) -> list[SObjectInfo]:
        """List all sObjects available in the Salesforce org.

        Returns:
            List of SObjectInfo with compact metadata for each sObject.
        """
        data = await self._request("GET", "/sobjects")
        return [
            self._parse_sobject_info(s)
            for s in data.get("sobjects", [])
        ]

    @action("Run a SOSL search")
    async def search(self, sosl: str) -> list[SalesforceRecord]:
        """Execute a SOSL (Salesforce Object Search Language) search.

        SOSL performs full-text searches across multiple sObjects
        simultaneously.

        Args:
            sosl: SOSL query string (e.g.,
                ``"FIND {Acme} IN ALL FIELDS RETURNING Account(Id, Name)"``).

        Returns:
            List of matching SalesforceRecord objects.
        """
        params: dict[str, Any] = {"q": sosl}
        data = await self._request("GET", "/search", params=params)

        # SOSL returns {"searchRecords": [...]}
        records_data = data.get("searchRecords", [])
        return [self._parse_record(r) for r in records_data]
