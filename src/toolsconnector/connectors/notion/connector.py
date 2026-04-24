"""Notion connector -- pages, databases, and blocks via the Notion API."""

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

from ._helpers import parse_block, parse_comment, parse_database, parse_page
from .types import (
    NotionBlock,
    NotionComment,
    NotionDatabase,
    NotionPage,
    NotionUser,
)

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
        "Connect to Notion to search, create, and manage pages, databases, and content blocks."
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
            toolsconnector.errors.APIError (subclass): On any non-2xx response.
                Maps to a typed exception by status: 401 -> InvalidCredentialsError
                or TokenExpiredError; 403 -> PermissionDeniedError; 404 -> NotFoundError;
                409 -> ConflictError; 400/422 -> ValidationError; 429 -> RateLimitError;
                5xx -> ServerError; other 4xx -> APIError. See
                toolsconnector.connectors._helpers.raise_typed_for_status for the full mapping.

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
            raise_typed_for_status(response, connector=self.name)
            return response.json()

    # ------------------------------------------------------------------
    # Actions -- Search & Pages
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

        pages = [parse_page(r) for r in data.get("results", [])]
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
        return parse_page(data)

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
        body: dict[str, Any] = {}

        if properties:
            body["parent"] = {"database_id": parent_id}
            body["properties"] = properties
            if "title" not in properties and "Name" not in properties:
                body["properties"]["title"] = {"title": [{"text": {"content": title}}]}
        else:
            body["parent"] = {"page_id": parent_id}
            body["properties"] = {"title": {"title": [{"text": {"content": title}}]}}

        if children:
            body["children"] = children

        data = await self._request("POST", "/pages", json=body)
        return parse_page(data)

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
        return parse_page(data)

    # ------------------------------------------------------------------
    # Actions -- Databases
    # ------------------------------------------------------------------

    @action("Get a database schema and metadata")
    async def get_database(self, database_id: str) -> NotionDatabase:
        """Retrieve a Notion database by its ID.

        Args:
            database_id: UUID of the database.

        Returns:
            The requested NotionDatabase with its schema.
        """
        data = await self._request("GET", f"/databases/{database_id}")
        return parse_database(data)

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

        data = await self._request("POST", f"/databases/{database_id}/query", json=body)

        pages = [parse_page(r) for r in data.get("results", [])]
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

    @action("Create a new database", dangerous=True)
    async def create_database(
        self,
        parent_id: str,
        title: str,
        properties: dict[str, Any],
    ) -> NotionDatabase:
        """Create a new database as a child of an existing page.

        Args:
            parent_id: UUID of the parent page.
            title: Title for the new database.
            properties: Database property schema.  Each key is a property
                name and each value is a property configuration object
                (e.g., ``{"Name": {"title": {}}, "Tags": {"multi_select":
                {"options": []}}}``).

        Returns:
            The newly created NotionDatabase.
        """
        body: dict[str, Any] = {
            "parent": {"page_id": parent_id},
            "title": [{"text": {"content": title}}],
            "properties": properties,
        }
        data = await self._request("POST", "/databases", json=body)
        return parse_database(data)

    # ------------------------------------------------------------------
    # Actions -- Blocks
    # ------------------------------------------------------------------

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

        data = await self._request("GET", f"/blocks/{block_id}/children", params=params)

        blocks = [parse_block(b) for b in data.get("results", [])]
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
        data = await self._request("PATCH", f"/blocks/{block_id}/children", json=body)

        return [parse_block(b) for b in data.get("results", [])]

    @action("Delete a block", dangerous=True)
    async def delete_block(self, block_id: str) -> None:
        """Delete a block by its ID.

        This is a destructive action.  The block and all of its children
        are moved to the trash and can be restored within 30 days via
        the Notion UI.

        Args:
            block_id: UUID of the block to delete.
        """
        await self._request("DELETE", f"/blocks/{block_id}")

    @action("Update a block's content")
    async def update_block(
        self,
        block_id: str,
        content: dict[str, Any],
    ) -> NotionBlock:
        """Update the content of an existing block.

        The ``content`` dict must match the shape expected by the block's
        type.  For example, to update a paragraph block, pass::

            {"paragraph": {"rich_text": [{"text": {"content": "new text"}}]}}

        Args:
            block_id: UUID of the block to update.
            content: Block-type-specific content payload.

        Returns:
            The updated NotionBlock.
        """
        data = await self._request("PATCH", f"/blocks/{block_id}", json=content)
        return parse_block(data)

    # ------------------------------------------------------------------
    # Actions -- Users
    # ------------------------------------------------------------------

    @action("List all users in the workspace")
    async def list_users(self) -> list[NotionUser]:
        """List all users (members and bots) in the workspace.

        Returns:
            List of NotionUser objects.
        """
        data = await self._request("GET", "/users")
        return [
            NotionUser(
                id=u["id"],
                name=u.get("name"),
                avatar_url=u.get("avatar_url"),
                type=u.get("type", "person"),
            )
            for u in data.get("results", [])
        ]

    @action("Get a single user by ID")
    async def get_user(self, user_id: str) -> NotionUser:
        """Retrieve a single workspace user by their ID.

        Args:
            user_id: UUID of the user to retrieve.

        Returns:
            The requested NotionUser.
        """
        data = await self._request("GET", f"/users/{user_id}")
        return NotionUser(
            id=data["id"],
            name=data.get("name"),
            avatar_url=data.get("avatar_url"),
            type=data.get("type", "person"),
        )

    # ------------------------------------------------------------------
    # Actions -- Comments
    # ------------------------------------------------------------------

    @action("List comments on a block or page")
    async def list_comments(
        self,
        block_id: str,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> PaginatedList[NotionComment]:
        """Retrieve comments on a block or page.

        Args:
            block_id: UUID of the block or page to list comments for.
            limit: Maximum results per page (max 100).
            cursor: Pagination cursor from a previous response.

        Returns:
            Paginated list of NotionComment objects.
        """
        params: dict[str, Any] = {
            "block_id": block_id,
            "page_size": min(limit, 100),
        }
        if cursor:
            params["start_cursor"] = cursor

        data = await self._request("GET", "/comments", params=params)

        comments = [parse_comment(c) for c in data.get("results", [])]
        has_more = data.get("has_more", False)
        next_cursor = data.get("next_cursor")

        return PaginatedList(
            items=comments,
            page_state=PageState(
                cursor=next_cursor,
                has_more=has_more,
            ),
            total_count=None,
        )

    @action("Add a comment to a page", dangerous=True)
    async def add_comment(
        self,
        page_id: str,
        text: str,
    ) -> NotionComment:
        """Add a new comment to a Notion page.

        Args:
            page_id: UUID of the page to comment on.
            text: Plain-text content of the comment.

        Returns:
            The newly created NotionComment.
        """
        body: dict[str, Any] = {
            "parent": {"page_id": page_id},
            "rich_text": [{"text": {"content": text}}],
        }
        data = await self._request("POST", "/comments", json=body)
        return parse_comment(data)

    # ------------------------------------------------------------------
    # Actions -- Database management (extended)
    # ------------------------------------------------------------------

    @action("Update a database's title, description, or properties")
    async def update_database(
        self,
        database_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        properties: Optional[dict[str, Any]] = None,
    ) -> NotionDatabase:
        """Update an existing Notion database.

        Args:
            database_id: UUID of the database to update.
            title: New title for the database, or ``None`` to keep
                the current title.
            description: New description text, or ``None`` to keep
                the current description.
            properties: Property schema updates.  Each key is a property
                name and each value is a property configuration object.
                Pass ``None`` for a property value to remove it.

        Returns:
            The updated NotionDatabase.
        """
        body: dict[str, Any] = {}
        if title is not None:
            body["title"] = [{"text": {"content": title}}]
        if description is not None:
            body["description"] = [{"text": {"content": description}}]
        if properties is not None:
            body["properties"] = properties

        data = await self._request("PATCH", f"/databases/{database_id}", json=body)
        return parse_database(data)

    # ------------------------------------------------------------------
    # Actions -- Page lifecycle
    # ------------------------------------------------------------------

    @action("Archive (soft-delete) a page", dangerous=True)
    async def archive_page(self, page_id: str) -> NotionPage:
        """Archive a Notion page by setting its ``archived`` flag to true.

        Archived pages are moved to the trash and can be restored
        within 30 days.

        Args:
            page_id: UUID of the page to archive.

        Returns:
            The archived NotionPage.
        """
        body: dict[str, Any] = {"archived": True}
        data = await self._request("PATCH", f"/pages/{page_id}", json=body)
        return parse_page(data)

    @action("Restore an archived page")
    async def restore_page(self, page_id: str) -> NotionPage:
        """Restore a previously archived Notion page.

        Args:
            page_id: UUID of the page to restore.

        Returns:
            The restored NotionPage with ``archived=False``.
        """
        body: dict[str, Any] = {"archived": False}
        data = await self._request("PATCH", f"/pages/{page_id}", json=body)
        return parse_page(data)

    # ------------------------------------------------------------------
    # Actions -- Blocks (extended)
    # ------------------------------------------------------------------

    @action("Get a single block by ID")
    async def get_block(self, block_id: str) -> NotionBlock:
        """Retrieve a single Notion block by its ID.

        Args:
            block_id: UUID of the block to retrieve.

        Returns:
            The requested NotionBlock.
        """
        data = await self._request("GET", f"/blocks/{block_id}")
        return parse_block(data)

    # ------------------------------------------------------------------
    # Actions -- Page properties
    # ------------------------------------------------------------------

    @action("Get a page property value by ID")
    async def get_page_property(
        self,
        page_id: str,
        property_id: str,
    ) -> dict[str, Any]:
        """Retrieve a specific property value from a Notion page.

        This endpoint is useful for paginated property types such as
        ``title``, ``rich_text``, ``relation``, and ``rollup`` where
        the page object truncates values.

        Args:
            page_id: UUID of the page.
            property_id: The ID of the property to retrieve (found in
                the page's ``properties`` dict under each property's
                ``id`` field).

        Returns:
            Raw property value dict from the Notion API.  The shape
            depends on the property type.
        """
        data = await self._request("GET", f"/pages/{page_id}/properties/{property_id}")
        return data
