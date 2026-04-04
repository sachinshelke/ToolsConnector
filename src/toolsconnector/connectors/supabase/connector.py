"""Supabase connector -- PostgREST-based table operations and RPC.

Uses the Supabase REST API (PostgREST) with API key + service role key
authentication.  Credentials should be ``anon_key:service_role_key``.

Filters use PostgREST query-parameter syntax (e.g. ``{"id": "eq.5"}``).
Pagination is handled via the HTTP ``Range`` header.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import httpx

from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import (
    ConnectorCategory,
    ProtocolType,
    RateLimitSpec,
)
from toolsconnector.types import PageState, PaginatedList

from .types import SupabaseRecord, SupabaseRPCResult, SupabaseTable

logger = logging.getLogger("toolsconnector.supabase")


class Supabase(BaseConnector):
    """Connect to Supabase to query and mutate tables via PostgREST.

    Credentials must be provided as ``anon_key:service_role_key``.  The
    anon key is sent via the ``apikey`` header and the service role key
    via the ``Authorization: Bearer`` header.

    The ``base_url`` should point to the PostgREST endpoint, e.g.
    ``https://your-project.supabase.co/rest/v1``.
    """

    name = "supabase"
    display_name = "Supabase"
    category = ConnectorCategory.DATABASE
    protocol = ProtocolType.REST
    base_url = "https://your-project.supabase.co/rest/v1"
    description = (
        "Connect to Supabase to query tables, insert/update/delete "
        "records, call RPC functions, and inspect schema."
    )
    _rate_limit_config = RateLimitSpec(rate=500, period=1, burst=100)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Initialise credentials and httpx client."""
        creds = self._credentials or ":"
        if isinstance(creds, str):
            parts = creds.split(":", 1)
            anon_key = parts[0]
            service_role_key = parts[1] if len(parts) > 1 else anon_key
        else:
            anon_key = creds.get("anon_key", "")
            service_role_key = creds.get("service_role_key", anon_key)

        self._anon_key = anon_key
        self._service_role_key = service_role_key

        headers: dict[str, str] = {
            "apikey": self._anon_key,
            "Authorization": f"Bearer {self._service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
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
        extra_headers: Optional[dict[str, str]] = None,
    ) -> httpx.Response:
        """Send an authenticated request to the Supabase REST API.

        Args:
            method: HTTP method (GET, POST, PATCH, DELETE).
            path: API path relative to base_url.
            params: Query parameters.
            json_body: JSON request body.
            extra_headers: Additional headers to merge in.

        Returns:
            httpx.Response object.

        Raises:
            httpx.HTTPStatusError: On 4xx/5xx responses.
        """
        kwargs: dict[str, Any] = {"method": method, "url": path}
        if params:
            kwargs["params"] = params
        if json_body is not None:
            kwargs["content"] = json.dumps(json_body)
        if extra_headers:
            kwargs["headers"] = extra_headers

        resp = await self._client.request(**kwargs)
        resp.raise_for_status()
        return resp

    # ------------------------------------------------------------------
    # Actions -- Query / Read
    # ------------------------------------------------------------------

    @action("Query records from a Supabase table")
    async def query_table(
        self,
        table: str,
        select: Optional[str] = None,
        filter: Optional[dict[str, str]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> PaginatedList[SupabaseRecord]:
        """Query records from a table with optional select, filter, and pagination.

        Filters use PostgREST syntax, e.g. ``{"age": "gt.18", "name": "eq.Alice"}``.

        Args:
            table: Table name.
            select: Comma-separated column names (PostgREST select).
            filter: Dict of column-name to PostgREST filter expression.
            limit: Maximum number of records to return.
            offset: Number of records to skip.

        Returns:
            Paginated list of SupabaseRecord objects.
        """
        params: dict[str, Any] = {}
        if select:
            params["select"] = select
        if filter:
            params.update(filter)

        range_start = offset
        range_end = offset + limit - 1
        extra_headers = {
            "Range": f"{range_start}-{range_end}",
            "Prefer": "count=exact",
        }

        resp = await self._request(
            "GET", f"/{table}", params=params, extra_headers=extra_headers,
        )
        rows = resp.json()

        content_range = resp.headers.get("content-range", "")
        total_count: Optional[int] = None
        has_more = False
        if "/" in content_range:
            total_str = content_range.split("/")[-1]
            if total_str != "*":
                total_count = int(total_str)
                has_more = (offset + limit) < total_count

        items = [SupabaseRecord(data=row) for row in rows]
        page_state = PageState(
            has_more=has_more,
            cursor=str(offset + limit) if has_more else None,
        )

        result = PaginatedList(
            items=items, page_state=page_state, total_count=total_count,
        )
        result._fetch_next = (
            (lambda o=offset + limit: self.aquery_table(
                table=table, select=select, filter=filter,
                limit=limit, offset=o,
            ))
            if has_more else None
        )
        return result

    @action("Get a single record from a Supabase table by ID")
    async def get_record(self, table: str, id: str) -> SupabaseRecord:
        """Retrieve a single record by its primary key.

        Args:
            table: Table name.
            id: Primary key value of the record.

        Returns:
            SupabaseRecord with the row data.
        """
        params: dict[str, str] = {"id": f"eq.{id}"}
        extra_headers = {"Accept": "application/vnd.pgrst.object+json"}

        resp = await self._request(
            "GET", f"/{table}", params=params, extra_headers=extra_headers,
        )
        return SupabaseRecord(data=resp.json())

    # ------------------------------------------------------------------
    # Actions -- Mutations
    # ------------------------------------------------------------------

    @action("Insert a record into a Supabase table")
    async def insert_record(
        self, table: str, data: dict[str, Any],
    ) -> SupabaseRecord:
        """Insert a new record into a table.

        Args:
            table: Table name.
            data: Dict of column-name to value for the new row.

        Returns:
            SupabaseRecord with the inserted row (including defaults).
        """
        resp = await self._request("POST", f"/{table}", json_body=data)
        rows = resp.json()
        row = rows[0] if isinstance(rows, list) else rows
        return SupabaseRecord(data=row)

    @action("Update a record in a Supabase table")
    async def update_record(
        self, table: str, id: str, data: dict[str, Any],
    ) -> SupabaseRecord:
        """Update an existing record by primary key.

        Args:
            table: Table name.
            id: Primary key value of the record to update.
            data: Dict of column-name to new value.

        Returns:
            SupabaseRecord with the updated row.
        """
        params: dict[str, str] = {"id": f"eq.{id}"}
        resp = await self._request(
            "PATCH", f"/{table}", params=params, json_body=data,
        )
        rows = resp.json()
        row = rows[0] if isinstance(rows, list) else rows
        return SupabaseRecord(data=row)

    @action("Upsert a record into a Supabase table")
    async def upsert_record(
        self, table: str, data: dict[str, Any],
    ) -> SupabaseRecord:
        """Insert or update a record (upsert).

        If a row with the same primary key exists it will be updated;
        otherwise a new row is inserted.

        Args:
            table: Table name.
            data: Dict of column-name to value.

        Returns:
            SupabaseRecord with the upserted row.
        """
        extra_headers = {"Prefer": "return=representation,resolution=merge-duplicates"}
        resp = await self._request(
            "POST", f"/{table}", json_body=data, extra_headers=extra_headers,
        )
        rows = resp.json()
        row = rows[0] if isinstance(rows, list) else rows
        return SupabaseRecord(data=row)

    @action("Delete a record from a Supabase table", dangerous=True)
    async def delete_record(self, table: str, id: str) -> None:
        """Delete a record by primary key.

        Args:
            table: Table name.
            id: Primary key value of the record to delete.
        """
        params: dict[str, str] = {"id": f"eq.{id}"}
        await self._request("DELETE", f"/{table}", params=params)

    # ------------------------------------------------------------------
    # Actions -- RPC
    # ------------------------------------------------------------------

    @action("Call a Supabase RPC (stored procedure)")
    async def rpc(
        self,
        function_name: str,
        params: Optional[dict[str, Any]] = None,
    ) -> SupabaseRPCResult:
        """Invoke a Postgres function via the PostgREST RPC endpoint.

        Args:
            function_name: Name of the Postgres function.
            params: Keyword arguments to pass to the function.

        Returns:
            SupabaseRPCResult with the function return value.
        """
        resp = await self._request(
            "POST", f"/rpc/{function_name}", json_body=params or {},
        )
        return SupabaseRPCResult(result=resp.json())

    # ------------------------------------------------------------------
    # Actions -- Schema introspection
    # ------------------------------------------------------------------

    @action("List tables available in the Supabase project")
    async def list_tables(self) -> list[SupabaseTable]:
        """List tables by fetching the PostgREST OpenAPI schema.

        This queries the root ``/`` endpoint which returns an OpenAPI
        spec describing available tables and their columns.

        Returns:
            List of SupabaseTable objects with name and column info.
        """
        resp = await self._request("GET", "/", extra_headers={"Accept": "application/json"})
        spec = resp.json()

        tables: list[SupabaseTable] = []
        definitions = spec.get("definitions", {})
        for table_name, table_def in definitions.items():
            props = table_def.get("properties", {})
            columns = list(props.keys())
            tables.append(SupabaseTable(
                name=table_name,
                description=table_def.get("description"),
                columns=columns,
            ))

        return tables
