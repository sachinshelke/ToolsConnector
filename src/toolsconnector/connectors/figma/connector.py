"""Figma connector -- files, comments, projects, components, and images.

Uses the Figma REST API v1 with personal access token authentication
via the ``X-FIGMA-TOKEN`` header.
"""

from __future__ import annotations

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

from ._parsers import (
    parse_comment,
    parse_component,
    parse_component_set,
    parse_file,
    parse_image,
    parse_page,
    parse_project,
    parse_project_file,
    parse_style,
    parse_version,
)
from .types import (
    FigmaComment,
    FigmaComponent,
    FigmaComponentSet,
    FigmaFile,
    FigmaImage,
    FigmaPage,
    FigmaProject,
    FigmaProjectFile,
    FigmaStyle,
    FigmaVersion,
)

logger = logging.getLogger("toolsconnector.figma")


class Figma(BaseConnector):
    """Connect to Figma to access files, comments, projects, and components.

    Supports personal access token authentication via the
    ``X-FIGMA-TOKEN`` header.
    """

    name = "figma"
    display_name = "Figma"
    category = ConnectorCategory.PRODUCTIVITY
    protocol = ProtocolType.REST
    base_url = "https://api.figma.com/v1"
    description = (
        "Connect to Figma to access design files, comments, "
        "projects, components, and exported images."
    )
    _rate_limit_config = RateLimitSpec(rate=30, period=60, burst=10)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Initialise the httpx async client with Figma access token."""
        token = self._credentials or ""

        headers: dict[str, str] = {
            "X-FIGMA-TOKEN": token,
            "Accept": "application/json",
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
        json_body: Optional[dict[str, Any]] = None,
    ) -> httpx.Response:
        """Send an authenticated request to the Figma API.

        Args:
            method: HTTP method (GET, POST, etc.).
            path: API path relative to base_url.
            params: Query parameters.
            json_body: JSON body for POST requests.

        Returns:
            httpx.Response object.

        Raises:
            httpx.HTTPStatusError: On 4xx/5xx responses.
        """
        resp = await self._client.request(
            method, path, params=params, json=json_body,
        )
        resp.raise_for_status()
        return resp

    # ------------------------------------------------------------------
    # Actions -- Files
    # ------------------------------------------------------------------

    @action("Get a Figma file by key")
    async def get_file(self, file_key: str) -> FigmaFile:
        """Retrieve metadata for a Figma file.

        Args:
            file_key: The file key from the Figma URL.

        Returns:
            FigmaFile object with file metadata.
        """
        resp = await self._request("GET", f"/files/{file_key}")
        return parse_file(resp.json())

    @action("List version history for a Figma file")
    async def list_file_versions(
        self,
        file_key: str,
        limit: Optional[int] = None,
    ) -> PaginatedList[FigmaVersion]:
        """List the version history of a Figma file.

        Args:
            file_key: The file key from the Figma URL.
            limit: Maximum number of versions to return.

        Returns:
            Paginated list of FigmaVersion objects.
        """
        params: dict[str, Any] = {}
        if limit is not None:
            params["page_size"] = limit

        resp = await self._request(
            "GET", f"/files/{file_key}/versions", params=params,
        )
        body = resp.json()
        versions_raw = body.get("versions") or []
        items = [parse_version(v) for v in versions_raw]

        # Figma versions use cursor pagination via pagination field
        pagination = body.get("pagination") or {}
        next_cursor = pagination.get("next_page")
        has_more = bool(next_cursor)

        return PaginatedList(
            items=items,
            page_state=PageState(has_more=has_more, cursor=next_cursor),
        )

    # ------------------------------------------------------------------
    # Actions -- Comments
    # ------------------------------------------------------------------

    @action("Get comments on a Figma file")
    async def get_comments(self, file_key: str) -> PaginatedList[FigmaComment]:
        """Retrieve all comments on a Figma file.

        Args:
            file_key: The file key from the Figma URL.

        Returns:
            List of FigmaComment objects.
        """
        resp = await self._request("GET", f"/files/{file_key}/comments")
        body = resp.json()
        comments_raw = body.get("comments") or []
        items = [parse_comment(c) for c in comments_raw]

        return PaginatedList(
            items=items,
            page_state=PageState(has_more=False),
        )

    @action("Post a comment on a Figma file", dangerous=True)
    async def post_comment(
        self,
        file_key: str,
        message: str,
        client_meta: Optional[dict[str, Any]] = None,
    ) -> FigmaComment:
        """Post a new comment on a Figma file.

        Args:
            file_key: The file key from the Figma URL.
            message: The comment message text.
            client_meta: Optional positioning data (x, y, node_id, etc.).

        Returns:
            The created FigmaComment object.
        """
        payload: dict[str, Any] = {"message": message}
        if client_meta is not None:
            payload["client_meta"] = client_meta

        resp = await self._request(
            "POST", f"/files/{file_key}/comments",
            json_body=payload,
        )
        return parse_comment(resp.json())

    # ------------------------------------------------------------------
    # Actions -- Projects
    # ------------------------------------------------------------------

    @action("List projects for a Figma team")
    async def list_projects(
        self, team_id: str,
    ) -> PaginatedList[FigmaProject]:
        """List all projects in a Figma team.

        Args:
            team_id: The Figma team ID.

        Returns:
            List of FigmaProject objects.
        """
        resp = await self._request("GET", f"/teams/{team_id}/projects")
        body = resp.json()
        projects_raw = body.get("projects") or []
        items = [parse_project(p) for p in projects_raw]

        return PaginatedList(
            items=items,
            page_state=PageState(has_more=False),
        )

    @action("List files in a Figma project")
    async def list_project_files(
        self, project_id: str,
    ) -> PaginatedList[FigmaProjectFile]:
        """List all files in a Figma project.

        Args:
            project_id: The Figma project ID.

        Returns:
            List of FigmaProjectFile objects.
        """
        resp = await self._request("GET", f"/projects/{project_id}/files")
        body = resp.json()
        files_raw = body.get("files") or []
        items = [parse_project_file(f) for f in files_raw]

        return PaginatedList(
            items=items,
            page_state=PageState(has_more=False),
        )

    # ------------------------------------------------------------------
    # Actions -- Images
    # ------------------------------------------------------------------

    @action("Export images from a Figma file")
    async def get_image(
        self,
        file_key: str,
        ids: str,
        format: Optional[str] = None,
    ) -> PaginatedList[FigmaImage]:
        """Export rendered images for specific nodes in a Figma file.

        Args:
            file_key: The file key from the Figma URL.
            ids: Comma-separated list of node IDs to render.
            format: Image format (``jpg``, ``png``, ``svg``, ``pdf``).

        Returns:
            List of FigmaImage objects with download URLs.
        """
        params: dict[str, Any] = {"ids": ids}
        if format is not None:
            params["format"] = format

        resp = await self._request(
            "GET", f"/images/{file_key}", params=params,
        )
        body = resp.json()
        images_map = body.get("images") or {}
        err = body.get("err")

        items = [
            parse_image(node_id, url, err)
            for node_id, url in images_map.items()
        ]

        return PaginatedList(
            items=items,
            page_state=PageState(has_more=False),
        )

    # ------------------------------------------------------------------
    # Actions -- Components
    # ------------------------------------------------------------------

    @action("List components in a Figma file")
    async def list_components(
        self, file_key: str,
    ) -> PaginatedList[FigmaComponent]:
        """List all published components in a Figma file.

        Args:
            file_key: The file key from the Figma URL.

        Returns:
            List of FigmaComponent objects.
        """
        resp = await self._request(
            "GET", f"/files/{file_key}/components",
        )
        body = resp.json()
        meta = body.get("meta") or {}
        components_raw = meta.get("components") or []
        items = [parse_component(c) for c in components_raw]

        return PaginatedList(
            items=items,
            page_state=PageState(has_more=False),
        )

    # ------------------------------------------------------------------
    # Actions -- File nodes
    # ------------------------------------------------------------------

    @action("Get specific nodes from a Figma file")
    async def get_file_nodes(
        self,
        file_key: str,
        ids: list[str],
    ) -> dict[str, Any]:
        """Get specific nodes from a Figma file by their IDs.

        Args:
            file_key: The Figma file key.
            ids: List of node IDs to retrieve.

        Returns:
            Dict with node data keyed by node ID.
        """
        resp = await self._request(
            "GET", f"/files/{file_key}/nodes",
            params={"ids": ",".join(ids)},
        )
        body = resp.json()
        return body.get("nodes", {})

    # ------------------------------------------------------------------
    # Actions -- Comment management (extended)
    # ------------------------------------------------------------------

    @action("Delete a comment from a Figma file", dangerous=True)
    async def delete_comment(
        self, file_key: str, comment_id: str,
    ) -> bool:
        """Delete a comment from a Figma file.

        Args:
            file_key: The Figma file key.
            comment_id: The comment ID to delete.

        Returns:
            True if the comment was deleted.
        """
        resp = await self._request(
            "DELETE", f"/files/{file_key}/comments/{comment_id}",
        )
        return resp.status_code in (200, 204)

    # ------------------------------------------------------------------
    # Actions -- Team projects
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Actions -- Component details
    # ------------------------------------------------------------------

    @action("Get a specific component from a Figma file")
    async def get_component(
        self,
        file_key: str,
        component_id: str,
    ) -> FigmaComponent:
        """Retrieve a single component by its node ID from a file.

        Args:
            file_key: The file key from the Figma URL.
            component_id: The node ID of the component.

        Returns:
            FigmaComponent object.
        """
        resp = await self._request(
            "GET", f"/files/{file_key}/nodes",
            params={"ids": component_id},
        )
        body = resp.json()
        nodes = body.get("nodes", {})
        node_data = nodes.get(component_id, {})
        doc = node_data.get("document", {})
        return FigmaComponent(
            key=doc.get("id", component_id),
            name=doc.get("name", ""),
            description=doc.get("description"),
            node_id=component_id,
            file_key=file_key,
        )

    # ------------------------------------------------------------------
    # Actions -- Styles
    # ------------------------------------------------------------------

    @action("List styles in a Figma file")
    async def get_file_styles(
        self, file_key: str,
    ) -> list[FigmaStyle]:
        """List all published styles (colors, text, effects) in a file.

        Args:
            file_key: The file key from the Figma URL.

        Returns:
            List of FigmaStyle objects.
        """
        resp = await self._request(
            "GET", f"/files/{file_key}/styles",
        )
        body = resp.json()
        meta = body.get("meta", {})
        return [parse_style(s) for s in meta.get("styles", [])]

    # ------------------------------------------------------------------
    # Actions -- File pages
    # ------------------------------------------------------------------

    @action("Get pages in a Figma file")
    async def get_file_pages(
        self, file_key: str,
    ) -> list[dict[str, Any]]:
        """Get the page structure (top-level canvases) of a Figma file.

        Args:
            file_key: The file key from the Figma URL.

        Returns:
            List of page dicts with id, name, and child count.
        """
        resp = await self._request(
            "GET", f"/files/{file_key}",
            params={"depth": "1"},
        )
        body = resp.json()
        document = body.get("document", {})
        children = document.get("children", [])
        return [
            {
                "id": page.get("id"),
                "name": page.get("name"),
                "type": page.get("type"),
                "child_count": len(page.get("children", [])),
            }
            for page in children
        ]

    @action("List projects in a team")
    async def list_team_projects(
        self,
        team_id: str,
        limit: Optional[int] = None,
    ) -> list[FigmaProject]:
        """List projects within a team.

        Args:
            team_id: The Figma team ID.
            limit: Maximum number of projects to return.

        Returns:
            List of FigmaProject objects.
        """
        resp = await self._request(
            "GET", f"/teams/{team_id}/projects",
        )
        body = resp.json()
        projects = [parse_project(p) for p in body.get("projects", [])]
        if limit is not None:
            projects = projects[:limit]
        return projects
