"""Airtable connector -- records, bases, and schema operations.

Uses the Airtable REST API v0 with personal access token (Bearer)
authentication.  Pagination uses offset tokens returned in the response.
"""

from __future__ import annotations

import logging
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

from .types import AirtableBase, AirtableField, AirtableRecord, AirtableTable, AirtableWebhook

logger = logging.getLogger("toolsconnector.airtable")


class Airtable(BaseConnector):
    """Connect to Airtable to manage bases, tables, and records.

    Credentials should be a personal access token (PAT) string.
    The token is sent via the ``Authorization: Bearer`` header.
    """

    name = "airtable"
    display_name = "Airtable"
    category = ConnectorCategory.DATABASE
    protocol = ProtocolType.REST
    base_url = "https://api.airtable.com/v0"
    description = (
        "Connect to Airtable to list bases, browse table schemas, "
        "and perform CRUD operations on records."
    )
    # Airtable rate limit: 5 requests per second per base.
    _rate_limit_config = RateLimitSpec(rate=5, period=1, burst=5)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Initialise the httpx client with Bearer auth."""
        token = self._credentials or ""

        headers: dict[str, str] = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        self._client = httpx.AsyncClient(
            base_url=self._base_url or self.__class__.base_url,
            headers=headers,
            timeout=self._timeout,
        )

    async def _teardown(self) -> None:
        """Close the httpx client."""
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
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[Any] = None,
    ) -> httpx.Response:
        """Send an authenticated request to the Airtable API.

        Args:
            method: HTTP method.
            path: API path relative to base_url.
            params: Query parameters.
            json_body: JSON request body.

        Returns:
            httpx.Response object.

        Raises:
            toolsconnector.errors.APIError (subclass): On any non-2xx response.
                Maps to a typed exception by status: 401 -> InvalidCredentialsError
                or TokenExpiredError; 403 -> PermissionDeniedError; 404 -> NotFoundError;
                409 -> ConflictError; 400/422 -> ValidationError; 429 -> RateLimitError;
                5xx -> ServerError; other 4xx -> APIError. See
                toolsconnector.connectors._helpers.raise_typed_for_status for the full mapping.
        """
        kwargs: dict[str, Any] = {"method": method, "url": path}
        if params:
            kwargs["params"] = params
        if json_body is not None:
            kwargs["json"] = json_body

        resp = await self._client.request(**kwargs)
        raise_typed_for_status(resp, connector=self.name)
        return resp

    # ------------------------------------------------------------------
    # Actions -- Bases & Schema
    # ------------------------------------------------------------------

    @action("List all accessible Airtable bases")
    async def list_bases(self) -> list[AirtableBase]:
        """List all bases the token has access to.

        Uses the Airtable Meta API endpoint.

        Returns:
            List of AirtableBase objects.
        """
        # The meta API lives under a different path prefix.
        resp = await self._client.get(
            "https://api.airtable.com/v0/meta/bases",
        )
        raise_typed_for_status(resp, connector=self.name)
        data = resp.json()

        return [
            AirtableBase(
                id=b.get("id", ""),
                name=b.get("name", ""),
                permission_level=b.get("permissionLevel"),
            )
            for b in data.get("bases", [])
        ]

    @action("Get the schema of an Airtable base")
    async def get_base_schema(self, base_id: str) -> list[AirtableTable]:
        """Retrieve the schema (tables and fields) of a base.

        Args:
            base_id: Airtable base ID (e.g. ``appXXXXXXXXXXXXXX``).

        Returns:
            List of AirtableTable objects with field metadata.
        """
        resp = await self._client.get(
            f"https://api.airtable.com/v0/meta/bases/{base_id}/tables",
        )
        raise_typed_for_status(resp, connector=self.name)
        data = resp.json()

        tables: list[AirtableTable] = []
        for t in data.get("tables", []):
            fields = [
                AirtableField(
                    id=f.get("id"),
                    name=f.get("name", ""),
                    type=f.get("type"),
                    description=f.get("description"),
                )
                for f in t.get("fields", [])
            ]
            tables.append(
                AirtableTable(
                    id=t.get("id"),
                    name=t.get("name", ""),
                    description=t.get("description"),
                    fields=fields,
                )
            )

        return tables

    # ------------------------------------------------------------------
    # Actions -- Records (Read)
    # ------------------------------------------------------------------

    @action("List records from an Airtable table")
    async def list_records(
        self,
        base_id: str,
        table_name: str,
        fields: Optional[list[str]] = None,
        filter_formula: Optional[str] = None,
        sort: Optional[list[dict[str, str]]] = None,
        limit: int = 100,
        offset: Optional[str] = None,
    ) -> PaginatedList[AirtableRecord]:
        """List records with optional field selection, filtering, and sorting.

        Args:
            base_id: Airtable base ID.
            table_name: Table name or ID.
            fields: List of field names to include in the response.
            filter_formula: Airtable formula for filtering records.
            sort: List of sort specs, e.g. ``[{"field": "Name", "direction": "asc"}]``.
            limit: Maximum records per page (max 100).
            offset: Pagination offset token from a previous response.

        Returns:
            Paginated list of AirtableRecord objects.
        """
        params: dict[str, Any] = {
            "pageSize": min(limit, 100),
        }
        if fields:
            for i, f in enumerate(fields):
                params[f"fields[{i}]"] = f
        if filter_formula:
            params["filterByFormula"] = filter_formula
        if sort:
            for i, s in enumerate(sort):
                params[f"sort[{i}][field]"] = s.get("field", "")
                params[f"sort[{i}][direction]"] = s.get("direction", "asc")
        if offset:
            params["offset"] = offset

        resp = await self._request(
            "GET",
            f"/{base_id}/{table_name}",
            params=params,
        )
        data = resp.json()

        items = [
            AirtableRecord(
                id=r.get("id", ""),
                created_time=r.get("createdTime"),
                fields=r.get("fields", {}),
            )
            for r in data.get("records", [])
        ]

        next_offset = data.get("offset")
        has_more = next_offset is not None
        page_state = PageState(has_more=has_more, cursor=next_offset)

        result = PaginatedList(items=items, page_state=page_state)
        result._fetch_next = (
            (
                lambda o=next_offset: self.alist_records(
                    base_id=base_id,
                    table_name=table_name,
                    fields=fields,
                    filter_formula=filter_formula,
                    sort=sort,
                    limit=limit,
                    offset=o,
                )
            )
            if has_more
            else None
        )
        return result

    @action("Get a single record from an Airtable table")
    async def get_record(
        self,
        base_id: str,
        table_name: str,
        record_id: str,
    ) -> AirtableRecord:
        """Retrieve a single record by ID.

        Args:
            base_id: Airtable base ID.
            table_name: Table name or ID.
            record_id: Record ID (e.g. ``recXXXXXXXXXXXXXX``).

        Returns:
            AirtableRecord with the record data.
        """
        resp = await self._request(
            "GET",
            f"/{base_id}/{table_name}/{record_id}",
        )
        r = resp.json()

        return AirtableRecord(
            id=r.get("id", ""),
            created_time=r.get("createdTime"),
            fields=r.get("fields", {}),
        )

    # ------------------------------------------------------------------
    # Actions -- Records (Write)
    # ------------------------------------------------------------------

    @action("Create a record in an Airtable table")
    async def create_record(
        self,
        base_id: str,
        table_name: str,
        fields: dict[str, Any],
    ) -> AirtableRecord:
        """Create a single record.

        Args:
            base_id: Airtable base ID.
            table_name: Table name or ID.
            fields: Dict of field name to value for the new record.

        Returns:
            AirtableRecord with the created record data.
        """
        body = {"fields": fields}
        resp = await self._request(
            "POST",
            f"/{base_id}/{table_name}",
            json_body=body,
        )
        r = resp.json()

        return AirtableRecord(
            id=r.get("id", ""),
            created_time=r.get("createdTime"),
            fields=r.get("fields", {}),
        )

    @action("Batch create records in an Airtable table")
    async def batch_create(
        self,
        base_id: str,
        table_name: str,
        records: list[dict[str, Any]],
    ) -> list[AirtableRecord]:
        """Create multiple records in a single request (max 10).

        Args:
            base_id: Airtable base ID.
            table_name: Table name or ID.
            records: List of dicts, each with a ``fields`` key.

        Returns:
            List of created AirtableRecord objects.
        """
        body = {
            "records": [{"fields": r} for r in records[:10]],
        }
        resp = await self._request(
            "POST",
            f"/{base_id}/{table_name}",
            json_body=body,
        )
        data = resp.json()

        return [
            AirtableRecord(
                id=r.get("id", ""),
                created_time=r.get("createdTime"),
                fields=r.get("fields", {}),
            )
            for r in data.get("records", [])
        ]

    @action("Update a record in an Airtable table")
    async def update_record(
        self,
        base_id: str,
        table_name: str,
        record_id: str,
        fields: dict[str, Any],
    ) -> AirtableRecord:
        """Update an existing record (partial update via PATCH).

        Args:
            base_id: Airtable base ID.
            table_name: Table name or ID.
            record_id: Record ID to update.
            fields: Dict of field name to new value.

        Returns:
            AirtableRecord with the updated record data.
        """
        body = {"fields": fields}
        resp = await self._request(
            "PATCH",
            f"/{base_id}/{table_name}/{record_id}",
            json_body=body,
        )
        r = resp.json()

        return AirtableRecord(
            id=r.get("id", ""),
            created_time=r.get("createdTime"),
            fields=r.get("fields", {}),
        )

    @action("Delete a record from an Airtable table", dangerous=True)
    async def delete_record(
        self,
        base_id: str,
        table_name: str,
        record_id: str,
    ) -> None:
        """Delete a single record by ID.

        Args:
            base_id: Airtable base ID.
            table_name: Table name or ID.
            record_id: Record ID to delete.
        """
        await self._request(
            "DELETE",
            f"/{base_id}/{table_name}/{record_id}",
        )

    # ------------------------------------------------------------------
    # Actions -- Batch operations
    # ------------------------------------------------------------------

    @action("Delete multiple records from a table", dangerous=True)
    async def delete_records(
        self,
        base_id: str,
        table_name: str,
        record_ids: list[str],
    ) -> bool:
        """Delete multiple records by their IDs.

        Args:
            base_id: Airtable base ID.
            table_name: Table name or ID.
            record_ids: List of record IDs to delete (max 10 per call).

        Returns:
            True if the deletion was successful.
        """
        # Airtable expects repeated query params for batch delete:
        # ?records[]=id1&records[]=id2... (max 10 per call).
        query_parts = "&".join(f"records[]={rid}" for rid in record_ids[:10])
        resp = await self._request(
            "DELETE",
            f"/{base_id}/{table_name}?{query_parts}",
        )
        return resp.status_code == 200

    @action("Update multiple records in a table")
    async def update_records(
        self,
        base_id: str,
        table_name: str,
        records: list[dict[str, Any]],
    ) -> list[AirtableRecord]:
        """Update multiple records in a single request.

        Args:
            base_id: Airtable base ID.
            table_name: Table name or ID.
            records: List of dicts with ``id`` and ``fields`` keys.

        Returns:
            List of updated AirtableRecord objects.
        """
        body: dict[str, Any] = {"records": records}
        resp = await self._request(
            "PATCH",
            f"/{base_id}/{table_name}",
            json_body=body,
        )
        data = resp.json()
        return [
            AirtableRecord(
                id=r.get("id", ""),
                created_time=r.get("createdTime"),
                fields=r.get("fields", {}),
            )
            for r in data.get("records", [])
        ]

    # ------------------------------------------------------------------
    # Actions -- Webhooks
    # ------------------------------------------------------------------

    @action("List webhooks for a base")
    async def list_webhooks(
        self,
        base_id: str,
    ) -> list[AirtableWebhook]:
        """List all webhook subscriptions for a base.

        Args:
            base_id: Airtable base ID.

        Returns:
            List of AirtableWebhook objects.
        """
        resp = await self._request(
            "GET",
            f"/bases/{base_id}/webhooks",
        )
        data = resp.json()
        return [
            AirtableWebhook(
                id=w.get("id", ""),
                type=w.get("type"),
                is_hook_enabled=w.get("isHookEnabled", True),
                notification_url=w.get("notificationUrl"),
                expiration_time=w.get("expirationTime"),
                cursor_for_next_payload=w.get("cursorForNextPayload"),
            )
            for w in data.get("webhooks", [])
        ]

    # ------------------------------------------------------------------
    # Actions -- Meta API (tables, fields, collaborators)
    # ------------------------------------------------------------------

    @action("Get all tables in an Airtable base")
    async def get_base_tables(
        self,
        base_id: str,
    ) -> list[AirtableTable]:
        """Retrieve all tables and their fields from a base.

        Uses the Meta API endpoint ``/meta/bases/{base_id}/tables``.

        Args:
            base_id: Airtable base ID (e.g. ``appXXXXXXXXXXXXXX``).

        Returns:
            List of AirtableTable objects with field metadata.
        """
        resp = await self._client.get(
            f"https://api.airtable.com/v0/meta/bases/{base_id}/tables",
        )
        raise_typed_for_status(resp, connector=self.name)
        data = resp.json()

        tables: list[AirtableTable] = []
        for t in data.get("tables", []):
            fields = [
                AirtableField(
                    id=f.get("id"),
                    name=f.get("name", ""),
                    type=f.get("type"),
                    description=f.get("description"),
                )
                for f in t.get("fields", [])
            ]
            tables.append(
                AirtableTable(
                    id=t.get("id"),
                    name=t.get("name", ""),
                    description=t.get("description"),
                    fields=fields,
                )
            )

        return tables

    @action("Create a field in an Airtable table", dangerous=True)
    async def create_field(
        self,
        base_id: str,
        table_id: str,
        name: str,
        type: str,
        options: Optional[dict[str, Any]] = None,
    ) -> AirtableField:
        """Create a new field (column) in a table via the Meta API.

        Args:
            base_id: Airtable base ID.
            table_id: Table ID (e.g. ``tblXXXXXXXXXXXXXX``).
            name: Display name for the new field.
            type: Airtable field type (e.g. ``singleLineText``, ``number``).
            options: Optional type-specific configuration dict.

        Returns:
            AirtableField with the created field metadata.
        """
        body: dict[str, Any] = {"name": name, "type": type}
        if options:
            body["options"] = options

        resp = await self._client.post(
            f"https://api.airtable.com/v0/meta/bases/{base_id}/tables/{table_id}/fields",
            json=body,
        )
        raise_typed_for_status(resp, connector=self.name)
        f = resp.json()

        return AirtableField(
            id=f.get("id"),
            name=f.get("name", ""),
            type=f.get("type"),
            description=f.get("description"),
        )

    @action("Update a field in an Airtable table")
    async def update_field(
        self,
        base_id: str,
        table_id: str,
        field_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> AirtableField:
        """Update a field's name or description via the Meta API.

        Args:
            base_id: Airtable base ID.
            table_id: Table ID.
            field_id: Field ID (e.g. ``fldXXXXXXXXXXXXXX``).
            name: New display name for the field.
            description: New description for the field.

        Returns:
            AirtableField with the updated field metadata.
        """
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description

        resp = await self._client.patch(
            f"https://api.airtable.com/v0/meta/bases/{base_id}/tables/{table_id}/fields/{field_id}",
            json=body,
        )
        raise_typed_for_status(resp, connector=self.name)
        f = resp.json()

        return AirtableField(
            id=f.get("id"),
            name=f.get("name", ""),
            type=f.get("type"),
            description=f.get("description"),
        )

    @action("List collaborators on an Airtable base")
    async def list_collaborators(
        self,
        base_id: str,
    ) -> list[dict[str, Any]]:
        """List all collaborators who have access to a base.

        Uses the Meta API endpoint
        ``/meta/bases/{base_id}/collaborators``.

        Args:
            base_id: Airtable base ID.

        Returns:
            List of collaborator dicts with user info and permission level.
        """
        resp = await self._client.get(
            f"https://api.airtable.com/v0/meta/bases/{base_id}/collaborators",
        )
        raise_typed_for_status(resp, connector=self.name)
        data = resp.json()

        return data.get("collaborators", [])

    @action("Create a table in an Airtable base", dangerous=True)
    async def create_table(
        self,
        base_id: str,
        name: str,
        fields: list[dict[str, Any]],
        description: Optional[str] = None,
    ) -> AirtableTable:
        """Create a new table in a base via the Meta API.

        Each field dict should contain at minimum ``name`` and ``type``
        keys.  At least one field must be provided.

        Args:
            base_id: Airtable base ID.
            name: Display name for the new table.
            fields: List of field definition dicts (``name``, ``type``,
                and optional ``options``).
            description: Optional description for the table.

        Returns:
            AirtableTable with the created table metadata.
        """
        body: dict[str, Any] = {"name": name, "fields": fields}
        if description:
            body["description"] = description

        resp = await self._client.post(
            f"https://api.airtable.com/v0/meta/bases/{base_id}/tables",
            json=body,
        )
        raise_typed_for_status(resp, connector=self.name)
        t = resp.json()

        parsed_fields = [
            AirtableField(
                id=f.get("id"),
                name=f.get("name", ""),
                type=f.get("type"),
                description=f.get("description"),
            )
            for f in t.get("fields", [])
        ]

        return AirtableTable(
            id=t.get("id"),
            name=t.get("name", ""),
            description=t.get("description"),
            fields=parsed_fields,
        )

    # ------------------------------------------------------------------
    # Actions — Views
    # ------------------------------------------------------------------

    @action("List views in a table")
    async def list_views(
        self,
        base_id: str,
        table_id: str,
    ) -> list[dict[str, Any]]:
        """List all views in a table.

        Args:
            base_id: The base ID.
            table_id: The table ID or name.

        Returns:
            List of view dicts with id, name, type.
        """
        data = await self._request(
            "GET",
            f"/meta/bases/{base_id}/tables/{table_id}/views",
        )
        return data.get("views", [])

    @action("Get a specific view")
    async def get_view(
        self,
        base_id: str,
        table_id: str,
        view_id: str,
    ) -> dict[str, Any]:
        """Get details of a specific view.

        Args:
            base_id: The base ID.
            table_id: The table ID or name.
            view_id: The view ID.

        Returns:
            View dict with id, name, type, and configuration.
        """
        data = await self._request(
            "GET",
            f"/meta/bases/{base_id}/tables/{table_id}/views/{view_id}",
        )
        return data

    # ------------------------------------------------------------------
    # Actions — Comments
    # ------------------------------------------------------------------

    @action("List comments on a record")
    async def list_comments(
        self,
        base_id: str,
        table_name: str,
        record_id: str,
    ) -> list[dict[str, Any]]:
        """List all comments on a record.

        Args:
            base_id: The base ID.
            table_name: The table name or ID.
            record_id: The record ID.

        Returns:
            List of comment dicts.
        """
        data = await self._request(
            "GET",
            f"/{base_id}/{table_name}/{record_id}/comments",
        )
        return data.get("comments", [])

    @action("Create a comment on a record", dangerous=True)
    async def create_comment(
        self,
        base_id: str,
        table_name: str,
        record_id: str,
        text: str,
    ) -> dict[str, Any]:
        """Add a comment to a record.

        Args:
            base_id: The base ID.
            table_name: The table name or ID.
            record_id: The record ID.
            text: The comment text.

        Returns:
            The created comment dict.
        """
        data = await self._request(
            "POST",
            f"/{base_id}/{table_name}/{record_id}/comments",
            json={"text": text},
        )
        return data

    @action("Update a comment on a record", dangerous=True)
    async def update_comment(
        self,
        base_id: str,
        table_name: str,
        record_id: str,
        comment_id: str,
        text: str,
    ) -> dict[str, Any]:
        """Update an existing comment.

        Args:
            base_id: The base ID.
            table_name: The table name or ID.
            record_id: The record ID.
            comment_id: The comment ID to update.
            text: New comment text.

        Returns:
            The updated comment dict.
        """
        data = await self._request(
            "PATCH",
            f"/{base_id}/{table_name}/{record_id}/comments/{comment_id}",
            json={"text": text},
        )
        return data

    @action("Delete a comment on a record", dangerous=True)
    async def delete_comment(
        self,
        base_id: str,
        table_name: str,
        record_id: str,
        comment_id: str,
    ) -> None:
        """Delete a comment from a record.

        Args:
            base_id: The base ID.
            table_name: The table name or ID.
            record_id: The record ID.
            comment_id: The comment ID to delete.
        """
        await self._request(
            "DELETE",
            f"/{base_id}/{table_name}/{record_id}/comments/{comment_id}",
        )

    # ------------------------------------------------------------------
    # Actions — Table update
    # ------------------------------------------------------------------

    @action("Update a table", dangerous=True)
    async def update_table(
        self,
        base_id: str,
        table_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> dict[str, Any]:
        """Update a table's name or description.

        Args:
            base_id: The base ID.
            table_id: The table ID.
            name: New table name.
            description: New table description.

        Returns:
            Updated table dict.
        """
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        data = await self._request(
            "PATCH",
            f"/meta/bases/{base_id}/tables/{table_id}",
            json=payload,
        )
        return data

    # ------------------------------------------------------------------
    # Actions — Webhooks (expanded)
    # ------------------------------------------------------------------

    @action("Create a webhook", dangerous=True)
    async def create_webhook(
        self,
        base_id: str,
        notification_url: str,
        specification: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Create a webhook to receive notifications about changes.

        Args:
            base_id: The base ID.
            notification_url: URL to receive webhook notifications.
            specification: Optional filter specification for which
                changes to notify about.

        Returns:
            Created webhook dict with id, notification_url, etc.
        """
        payload: dict[str, Any] = {
            "notificationUrl": notification_url,
        }
        if specification:
            payload["specification"] = specification
        data = await self._request(
            "POST",
            f"/bases/{base_id}/webhooks",
            json=payload,
        )
        return data

    @action("Delete a webhook", dangerous=True)
    async def delete_webhook(
        self,
        base_id: str,
        webhook_id: str,
    ) -> None:
        """Delete a webhook.

        Args:
            base_id: The base ID.
            webhook_id: The webhook ID to delete.
        """
        await self._request(
            "DELETE",
            f"/bases/{base_id}/webhooks/{webhook_id}",
        )

    @action("List webhook payloads")
    async def list_webhook_payloads(
        self,
        base_id: str,
        webhook_id: str,
        cursor: Optional[str] = None,
    ) -> dict[str, Any]:
        """List payloads for a webhook (change history).

        Args:
            base_id: The base ID.
            webhook_id: The webhook ID.
            cursor: Pagination cursor from previous response.

        Returns:
            Dict with payloads list and cursor for pagination.
        """
        params: dict[str, Any] = {}
        if cursor:
            params["cursor"] = cursor
        data = await self._request(
            "GET",
            f"/bases/{base_id}/webhooks/{webhook_id}/payloads",
            params=params,
        )
        return data
