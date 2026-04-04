"""Notion connector -- pages, databases, and blocks via the Notion API."""

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

from .types import NotionBlock, NotionDatabase, NotionPage, NotionProperty


_NOTION_VERSION = "2022-06-28"


class Notion(BaseConnector):
    """Connect to Notion to manage pages, databases, and content blocks.

    Uses the Notion REST API with bearer-token authentication.
    Credentials should be a Notion integration token (string).
    """

    name = "notion"
    display_name = "Notion"
    category = ConnectorCategory.KNOWLEDGE
    protocol = ProtocolType.REST
    base_url = "https://api.notion.com/v1"
    description = (
        "Connect to Notion to search, create, and manage pages, "
        "databases, and content blocks."
    )
    _rate_limit_config = RateLimitSpec(rate=3, period=1, burst=3)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        """Build standard request headers for the Notion API."""
        return {
            "Authorization": f"Bearer {self._credentials}",
            "Notion-Version": _NOTION_VERSION,
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Execute an HTTP request against the Notion API.

        Args:
            method: HTTP method (GET, POST, PATCH, DELETE).
            path: API path relative to ``base_url``.
            json: JSON body payload.
            params: Query string parameters.

        Returns:
            Parsed JSON response dict.

        Raises:
            httpx.HTTPStatusError: On non-2xx responses.
        """
        url = f"{self._base_url}{path}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.request(
                method,
                url,
                headers=self._headers(),
                json=json,
                params=params,
            )
            response.raise_for_status()
            return response.json()

    # ------------------------------------------------------------------
    # Response parsers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_page(data: dict[str, Any]) -> NotionPage:
        """Parse a raw Notion page JSON into a NotionPage model."""
        props: dict[str, NotionProperty] = {}
        for key, val in data.get("properties", {}).items():
            props[key] = NotionProperty(**val)

        return NotionPage(
            id=data["id"],
            object=data.get("object", "page"),
            created_time=data.get("created_time"),
            last_edited_time=data.get("last_edited_time"),
            archived=data.get("archived", False),
            url=data.get("url"),
            parent=data.get("parent", {}),
            properties=props,
            icon=data.get("icon"),
            cover=data.get("cover"),
        )

    @staticmethod
    def _parse_block(data: dict[str, Any]) -> NotionBlock:
        """Parse a raw Notion block JSON into a NotionBlock model."""
        block_type = data.get("type", "")
        return NotionBlock(
            id=data["id"],
            object=data.get("object", "block"),
            type=block_type,
            created_time=data.get("created_time"),
            last_edited_time=data.get("last_edited_time"),
            archived=data.get("archived", False),
            has_children=data.get("has_children", False),
            parent=data.get("parent", {}),
            content=data.get(block_type, {}),
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    @action("Search pages and databases in the workspace")
    async def search(
        self,
        query: str = "",
        filter_type: Optional[str] = None,
        limit: int = 20,
        cursor: Optional[str] = None,
    ) -> PaginatedList[NotionPage]:
        """Search across all pages and databases the integration can access.

        Args:
            query: Text to search for in page titles and content.
            filter_type: Restrict to ``"page"`` or ``"database"``.
            limit: Maximum number of results per page.
            cursor: Pagination cursor from a previous response.

        Returns:
            Paginated list of matching Notion pages.
        """
        body: dict[str, Any] = {"query": query, "page_size": min(limit, 100)}
        if filter_type:
            body["filter"] = {"value": filter_type, "property": "object"}
        if cursor:
            body["start_cursor"] = cursor

        data = await self._request("POST", "/search", json=body)

        pages = [self._parse_page(r) for r in data.get("results", [])]
        has_more = data.get("has_more", False)
        next_cursor = data.get("next_cursor")

        return PaginatedList(
            items=pages,
            page_state=PageState(
                cursor=next_cursor,
                has_more=has_more,
            ),
            total_count=None,
        )

    @action("Get a single page by ID")
    async def get_page(self, page_id: str) -> NotionPage:
        """Retrieve a Notion page by its ID.

        Args:
            page_id: The UUID of the page to retrieve.

        Returns:
            The requested NotionPage.
        """
        data = await self._request("GET", f"/pages/{page_id}")
        return self._parse_page(data)

    @action("Create a new page", dangerous=True)
    async def create_page(
        self,
        parent_id: str,
        title: str,
        properties: Optional[dict[str, Any]] = None,
        children: Optional[list[dict[str, Any]]] = None,
    ) -> NotionPage:
        """Create a new page under a parent page or database.

        Args:
            parent_id: UUID of the parent page or database.
            title: Page title text.
            properties: Additional property values (database pages).
            children: Block children to populate the page body.

        Returns:
            The newly created NotionPage.
        """
        # Determine parent type: database IDs are typically passed when
        # creating pages inside databases; otherwise assume page parent.
        body: dict[str, Any] = {}

        # Default: treat as database parent.  Callers wanting a page
        # parent can pass ``properties`` with the full schema.
        if properties:
            body["parent"] = {"database_id": parent_id}
            body["properties"] = properties
            # Ensure title is in properties if not already set
            if "title" not in properties and "Name" not in properties:
                body["properties"]["title"] = {
                    "title": [{"text": {"content": title}}]
                }
        else:
            body["parent"] = {"page_id": parent_id}
            body["properties"] = {
                "title": {"title": [{"text": {"content": title}}]}
            }

        if children:
            body["children"] = children

        data = await self._request("POST", "/pages", json=body)
        return self._parse_page(data)

    @action("Update page properties")
    async def update_page(
        self,
        page_id: str,
        properties: dict[str, Any],
    ) -> NotionPage:
        """Update properties on an existing Notion page.

        Args:
            page_id: UUID of the page to update.
            properties: Dict of property names to new values, following
                the Notion property value schema.

        Returns:
            The updated NotionPage.
        """
        body: dict[str, Any] = {"properties": properties}
        data = await self._request("PATCH", f"/pages/{page_id}", json=body)
        return self._parse_page(data)

    @action("Get a database schema and metadata")
    async def get_database(self, database_id: str) -> NotionDatabase:
        """Retrieve a Notion database by its ID.

        Args:
            database_id: UUID of the database.

        Returns:
            The requested NotionDatabase with its schema.
        """
        data = await self._request("GET", f"/databases/{database_id}")
        from .types import NotionRichText

        title_items = [
            NotionRichText(**t) for t in data.get("title", [])
        ]
        desc_items = [
            NotionRichText(**d) for d in data.get("description", [])
        ]

        return NotionDatabase(
            id=data["id"],
            object=data.get("object", "database"),
            title=title_items,
            description=desc_items,
            created_time=data.get("created_time"),
            last_edited_time=data.get("last_edited_time"),
            archived=data.get("archived", False),
            url=data.get("url"),
            parent=data.get("parent", {}),
            properties=data.get("properties", {}),
            icon=data.get("icon"),
            cover=data.get("cover"),
            is_inline=data.get("is_inline", False),
        )

    @action("Query a database with optional filters and sorts")
    async def query_database(
        self,
        database_id: str,
        filter: Optional[dict[str, Any]] = None,
        sorts: Optional[list[dict[str, Any]]] = None,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> PaginatedList[NotionPage]:
        """Query a Notion database, optionally applying filters and sorts.

        Args:
            database_id: UUID of the database to query.
            filter: Notion filter object (compound or property filter).
            sorts: List of sort objects with ``property`` and ``direction``.
            limit: Maximum results per page (max 100).
            cursor: Pagination cursor from a previous response.

        Returns:
            Paginated list of pages (rows) matching the query.
        """
        body: dict[str, Any] = {"page_size": min(limit, 100)}
        if filter:
            body["filter"] = filter
        if sorts:
            body["sorts"] = sorts
        if cursor:
            body["start_cursor"] = cursor

        data = await self._request(
            "POST", f"/databases/{database_id}/query", json=body
        )

        pages = [self._parse_page(r) for r in data.get("results", [])]
        has_more = data.get("has_more", False)
        next_cursor = data.get("next_cursor")

        return PaginatedList(
            items=pages,
            page_state=PageState(
                cursor=next_cursor,
                has_more=has_more,
            ),
            total_count=None,
        )

    @action("Get child blocks of a page or block")
    async def get_block_children(
        self,
        block_id: str,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> PaginatedList[NotionBlock]:
        """Retrieve the child blocks of a given block or page.

        Args:
            block_id: UUID of the parent block or page.
            limit: Maximum blocks per page (max 100).
            cursor: Pagination cursor from a previous response.

        Returns:
            Paginated list of child NotionBlock objects.
        """
        params: dict[str, Any] = {"page_size": min(limit, 100)}
        if cursor:
            params["start_cursor"] = cursor

        data = await self._request(
            "GET", f"/blocks/{block_id}/children", params=params
        )

        blocks = [self._parse_block(b) for b in data.get("results", [])]
        has_more = data.get("has_more", False)
        next_cursor = data.get("next_cursor")

        return PaginatedList(
            items=blocks,
            page_state=PageState(
                cursor=next_cursor,
                has_more=has_more,
            ),
            total_count=None,
        )

    @action("Append child blocks to a page or block", dangerous=True)
    async def append_block_children(
        self,
        block_id: str,
        children: list[dict[str, Any]],
    ) -> list[NotionBlock]:
        """Append new child blocks to a page or existing block.

        Args:
            block_id: UUID of the parent block or page.
            children: List of block objects to append, following
                the Notion block schema (e.g., paragraph, heading,
                to_do, bulleted_list_item).

        Returns:
            List of newly created NotionBlock objects.
        """
        body: dict[str, Any] = {"children": children}
        data = await self._request(
            "PATCH", f"/blocks/{block_id}/children", json=body
        )

        return [self._parse_block(b) for b in data.get("results", [])]
