"""Confluence connector -- manage pages and spaces via the Atlassian v2 REST API.

Uses httpx for direct HTTP calls against the Confluence Cloud REST API v2.
Expects a ``"email:api_token"`` string passed as ``credentials``, which is
base64-encoded for HTTP Basic authentication.
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Optional

import httpx

from toolsconnector.errors import APIError, NotFoundError, RateLimitError
from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import ConnectorCategory, ProtocolType, RateLimitSpec
from toolsconnector.types import PageState, PaginatedList

from .types import ConfluencePage, ConfluenceSpace, ConfluenceVersion

logger = logging.getLogger("toolsconnector.confluence")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_page(data: dict[str, Any]) -> ConfluencePage:
    """Parse a Confluence v2 API page JSON into a ConfluencePage model.

    Args:
        data: Raw JSON response from the pages endpoint.

    Returns:
        Populated ConfluencePage instance.
    """
    version_raw = data.get("version")
    version = None
    if version_raw:
        version = ConfluenceVersion(
            number=version_raw.get("number", 1),
            message=version_raw.get("message"),
            created_at=version_raw.get("createdAt"),
        )

    # Body may be nested under body.storage.value
    body_raw = data.get("body", {})
    body_storage = None
    if body_raw:
        storage = body_raw.get("storage", {})
        if storage:
            body_storage = storage.get("value")

    # _links for web URL
    links = data.get("_links", {})

    return ConfluencePage(
        id=data.get("id", ""),
        title=data.get("title", ""),
        space_id=data.get("spaceId"),
        status=data.get("status", "current"),
        body_storage=body_storage,
        parent_id=data.get("parentId"),
        version=version,
        created_at=data.get("createdAt"),
        author_id=data.get("authorId"),
        web_url=links.get("webui"),
    )


def _parse_space(data: dict[str, Any]) -> ConfluenceSpace:
    """Parse a Confluence v2 API space JSON into a ConfluenceSpace model.

    Args:
        data: Raw JSON response from the spaces endpoint.

    Returns:
        Populated ConfluenceSpace instance.
    """
    description_raw = data.get("description", {})
    description_text = None
    if description_raw:
        plain = description_raw.get("plain", {})
        if plain:
            description_text = plain.get("value")

    return ConfluenceSpace(
        id=data.get("id", ""),
        key=data.get("key"),
        name=data.get("name", ""),
        type=data.get("type"),
        status=data.get("status"),
        description=description_text,
        homepage_id=data.get("homepageId"),
    )


class Confluence(BaseConnector):
    """Connect to Confluence to manage pages and spaces.

    Requires an ``"email:api_token"`` string passed as ``credentials``.
    The base URL should point to a Confluence Cloud instance's v2 API
    (e.g., ``https://your-domain.atlassian.net/wiki/api/v2``).
    """

    name = "confluence"
    display_name = "Confluence"
    category = ConnectorCategory.KNOWLEDGE
    protocol = ProtocolType.REST
    base_url = "https://your-domain.atlassian.net/wiki/api/v2"
    description = "Connect to Confluence to manage pages and spaces via the Atlassian v2 API."
    _rate_limit_config = RateLimitSpec(rate=100, period=60, burst=20)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Initialise the persistent async HTTP client with Basic auth."""
        # credentials is "email:api_token" -- base64-encode for Basic auth
        creds_str = str(self._credentials)
        b64_creds = base64.b64encode(creds_str.encode("utf-8")).decode("ascii")

        self._client = httpx.AsyncClient(
            base_url=self._base_url or self.__class__.base_url,
            headers={
                "Authorization": f"Basic {b64_creds}",
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
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Execute an authenticated HTTP request against the Confluence v2 API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE).
            path: API path relative to base_url (e.g. ``/pages``).
            params: URL query parameters.
            json_body: JSON request body.

        Returns:
            Parsed JSON response as a dict.

        Raises:
            RateLimitError: When Confluence returns HTTP 429.
            NotFoundError: When the resource is not found (HTTP 404).
            APIError: For any other non-2xx status.
        """
        kwargs: dict[str, Any] = {}
        if params:
            kwargs["params"] = params
        if json_body is not None:
            kwargs["json"] = json_body

        response = await self._client.request(method, path, **kwargs)

        if response.status_code == 429:
            retry_after = float(response.headers.get("Retry-After", "60"))
            raise RateLimitError(
                "Confluence rate limit exceeded",
                connector="confluence",
                action=path,
                retry_after_seconds=retry_after,
            )
        if response.status_code == 404:
            raise NotFoundError(
                f"Resource not found: {path}",
                connector="confluence",
                action=path,
            )
        if response.status_code >= 400:
            detail = response.text[:500]
            raise APIError(
                f"Confluence error {response.status_code}: {detail}",
                connector="confluence",
                action=path,
                details={"status_code": response.status_code},
            )

        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    @action("List pages in a space or across all spaces")
    async def list_pages(
        self,
        space_id: Optional[str] = None,
        limit: int = 25,
        cursor: Optional[str] = None,
    ) -> PaginatedList[ConfluencePage]:
        """List Confluence pages.

        Args:
            space_id: Optional space ID to filter pages by.
            limit: Maximum number of pages per request (max 250).
            cursor: Cursor token for fetching the next page of results.

        Returns:
            Paginated list of ConfluencePage objects.
        """
        params: dict[str, Any] = {"limit": min(limit, 250)}
        if cursor:
            params["cursor"] = cursor

        if space_id:
            path = f"/spaces/{space_id}/pages"
        else:
            path = "/pages"

        data = await self._request("GET", path, params=params)

        pages = [_parse_page(p) for p in data.get("results", [])]
        links = data.get("_links", {})
        next_cursor = links.get("next")

        return PaginatedList(
            items=pages,
            page_state=PageState(
                cursor=next_cursor,
                has_more=next_cursor is not None,
            ),
        )

    @action("Get a single page by ID")
    async def get_page(self, page_id: str) -> ConfluencePage:
        """Retrieve a single Confluence page by its ID.

        Fetches the page with its body content in storage format.

        Args:
            page_id: The unique ID of the page.

        Returns:
            The requested ConfluencePage with body content.
        """
        data = await self._request(
            "GET",
            f"/pages/{page_id}",
            params={"body-format": "storage"},
        )
        return _parse_page(data)

    @action("Create a new page")
    async def create_page(
        self,
        space_id: str,
        title: str,
        body: str,
        parent_id: Optional[str] = None,
    ) -> ConfluencePage:
        """Create a new Confluence page.

        Args:
            space_id: The ID of the space to create the page in.
            title: Page title.
            body: Page body content in Confluence storage format (XHTML).
            parent_id: Optional parent page ID for nested pages.

        Returns:
            The created ConfluencePage object.
        """
        payload: dict[str, Any] = {
            "spaceId": space_id,
            "status": "current",
            "title": title,
            "body": {
                "representation": "storage",
                "value": body,
            },
        }
        if parent_id:
            payload["parentId"] = parent_id

        data = await self._request("POST", "/pages", json_body=payload)
        return _parse_page(data)

    @action("Update an existing page")
    async def update_page(
        self,
        page_id: str,
        title: str,
        body: str,
        version_number: int,
    ) -> ConfluencePage:
        """Update an existing Confluence page.

        The version number must match or increment the current version to
        prevent edit conflicts.

        Args:
            page_id: The unique ID of the page to update.
            title: New page title.
            body: New page body content in storage format (XHTML).
            version_number: New version number (current version + 1).

        Returns:
            The updated ConfluencePage object.
        """
        payload: dict[str, Any] = {
            "id": page_id,
            "status": "current",
            "title": title,
            "body": {
                "representation": "storage",
                "value": body,
            },
            "version": {
                "number": version_number,
                "message": f"Updated to version {version_number}",
            },
        }

        data = await self._request(
            "PUT",
            f"/pages/{page_id}",
            json_body=payload,
        )
        return _parse_page(data)

    @action("Delete a page", dangerous=True)
    async def delete_page(self, page_id: str) -> None:
        """Delete a Confluence page.

        Args:
            page_id: The unique ID of the page to delete.

        Warning:
            This permanently deletes the page. It cannot be undone.
        """
        await self._request("DELETE", f"/pages/{page_id}")

    @action("Search for pages using CQL")
    async def search(
        self,
        query: str,
        limit: int = 25,
        cursor: Optional[str] = None,
    ) -> PaginatedList[ConfluencePage]:
        """Search for Confluence pages using CQL (Confluence Query Language).

        The v2 API search endpoint uses a ``query`` parameter with the
        search term. For CQL, use the v1-compatible search or the
        ``/search`` endpoint which accepts natural-language queries.

        Args:
            query: Search query string.
            limit: Maximum results per page.
            cursor: Cursor token for fetching the next page.

        Returns:
            Paginated list of matching ConfluencePage objects.
        """
        params: dict[str, Any] = {
            "query": query,
            "limit": min(limit, 100),
        }
        if cursor:
            params["cursor"] = cursor

        # The v2 search endpoint returns pages directly
        data = await self._request("GET", "/search", params=params)

        pages: list[ConfluencePage] = []
        for result in data.get("results", []):
            # Search results may wrap pages differently
            page_data = result.get("page", result)
            pages.append(_parse_page(page_data))

        links = data.get("_links", {})
        next_cursor = links.get("next")

        return PaginatedList(
            items=pages,
            page_state=PageState(
                cursor=next_cursor,
                has_more=next_cursor is not None,
            ),
        )

    @action("List all spaces")
    async def list_spaces(
        self,
        limit: int = 25,
        cursor: Optional[str] = None,
    ) -> PaginatedList[ConfluenceSpace]:
        """List Confluence spaces.

        Args:
            limit: Maximum number of spaces per page (max 250).
            cursor: Cursor token for fetching the next page.

        Returns:
            Paginated list of ConfluenceSpace objects.
        """
        params: dict[str, Any] = {"limit": min(limit, 250)}
        if cursor:
            params["cursor"] = cursor

        data = await self._request("GET", "/spaces", params=params)

        spaces = [_parse_space(s) for s in data.get("results", [])]
        links = data.get("_links", {})
        next_cursor = links.get("next")

        return PaginatedList(
            items=spaces,
            page_state=PageState(
                cursor=next_cursor,
                has_more=next_cursor is not None,
            ),
        )

    @action("Get a single space by ID")
    async def get_space(self, space_id: str) -> ConfluenceSpace:
        """Retrieve details for a single Confluence space.

        Args:
            space_id: The unique ID of the space.

        Returns:
            The requested ConfluenceSpace object.
        """
        data = await self._request("GET", f"/spaces/{space_id}")
        return _parse_space(data)
