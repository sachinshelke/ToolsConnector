"""Notion connector — pages, databases, blocks, comments, and users via the Notion API.

Uses the Notion REST API at ``https://api.notion.com/v1`` with internal-integration
Bearer-token authentication (BYOK).

Endpoint surfaces
-----------------
This connector calls six Notion API resource families under ``api.notion.com/v1``,
all under the pinned ``Notion-Version: 2022-06-28`` header:

- ``/search`` — full-text search across all shared pages and databases.
- ``/pages``, ``/pages/{id}``, ``/pages/{id}/properties/{prop_id}`` — page CRUD,
  property retrieval, archive/restore.
- ``/databases``, ``/databases/{id}``, ``/databases/{id}/query`` — database
  schema + paginated query with filters and sorts.
- ``/blocks/{id}``, ``/blocks/{id}/children`` — block CRUD, append/list children.
- ``/users``, ``/users/{id}``, ``/users/me`` — workspace user list + bot identity.
- ``/comments``, ``/comments/{id}`` — comment CRUD on pages and discussion threads.

Pagination scheme
-----------------
Notion splits pagination by HTTP method:
- **POST** endpoints (search, query_database, create) take ``start_cursor`` +
  ``page_size`` in the JSON body.
- **GET** endpoints (block children, comments, users) take them as
  query-string params.

Both return ``has_more`` (bool) + ``next_cursor`` (str or null). Hard cap of
``100`` per page; the connector clamps requests above this.

Version pin rationale
---------------------
``Notion-Version: 2022-06-28`` is intentionally pinned. Newer versions
introduced breaking changes that would silently break this connector:

- **2025-09-03** — split ``/databases`` into ``/databases`` (containers) +
  ``/data_sources`` (queryable schema). Would break ``query_database`` and
  ``parse_database``.
- **2026-03-11** — renamed ``archived`` → ``in_trash`` everywhere. Would
  break ``archive_page``, ``restore_page``, and ``parse_page`` /
  ``parse_block`` / ``parse_database``.

Any "drive-by modernize" must bump the connector major version; the
``test_archive_page_sends_archived_field_for_pinned_version`` test is the
tripwire.

Error mapping
-------------
All HTTP non-2xx responses are mapped via the shared
``raise_typed_for_status`` helper, then augmented with Notion-specific
context. Catchable typed exceptions and their ``e.details["notion_code"]``:

==========================  ====================  ==========================
Typed exception             Notion code           Cause
==========================  ====================  ==========================
InvalidCredentialsError     unauthorized          Token invalid or revoked
PermissionDeniedError       restricted_resource   Capability not granted OR
                                                  page not shared with the
                                                  integration
NotFoundError               object_not_found      Page missing OR not shared
                                                  with the integration
                                                  (ambiguous — Notion's API
                                                  doesn't distinguish)
ValidationError             validation_error,     Body shape mismatch
                            invalid_json,
                            missing_version
ConflictError               conflict_error        Concurrent edit collision
RateLimitError              rate_limited          3 req/s average exceeded
ServerError                 service_unavailable,  Notion-side issue
                            internal_server_error
==========================  ====================  ==========================

Every typed error carries ``e.suggestion`` (string) with a one-line
actionable hint — the most useful field for surfacing capability gaps to
end users.

Out of scope (Notion-Version 2022-06-28 pin)
---------------------------------------------
Not exposed by this connector:

- File uploads (``/files/*``) — requires 2025-09-03+.
- Page moves (``PUT /pages/{id}/move``) — newer version.
- Markdown read/write (``/pages/{id}/markdown``) — newer version.
- Data sources (``/data_sources/*``) — 2025-09-03 split.
- Views (``/views/*``) — 2025-09-03+.
- Webhooks — UI-only subscription, no programmatic create endpoint.
- OAuth token exchange (``/oauth/*``) — BYOK; users bring their own token.
- Hard-delete pages (``DELETE /pages/{id}``) — ``archive_page`` is the safer
  path; destructive endpoint intentionally not exposed.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx

from toolsconnector.connectors._helpers import raise_typed_for_status
from toolsconnector.errors import (
    ConnectionError as ToolsConnectorConnectionError,
)
from toolsconnector.errors import (
    TimeoutError as ToolsConnectorTimeoutError,
)
from toolsconnector.errors import (
    ToolsConnectorError,
    TransportError,
    ValidationError,
)
from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import (
    ConnectorCategory,
    ProtocolType,
    RateLimitSpec,
)
from toolsconnector.types import PageState, PaginatedList

from ._helpers import parse_block, parse_comment, parse_database, parse_page, parse_user
from .types import (
    NotionBlock,
    NotionComment,
    NotionDatabase,
    NotionPage,
    NotionUser,
)

_NOTION_VERSION = "2022-06-28"

# Characters that must never appear in an ID interpolated into a URL path.
# Notion IDs are UUIDs (32 hex chars with optional dashes); property IDs may
# carry percent-encoded characters. None of these legitimately contain "/",
# "?", or "#". Allowing them would let a caller (or an AI agent) traverse to
# a different endpoint — e.g. aget_page("../users/me") would actually call
# /users/me instead of /pages/.... We refuse such IDs at the action boundary
# rather than letting the request leave the process.
_FORBIDDEN_ID_CHARS = ("/", "?", "#")


def _validate_id(value: str, name: str) -> str:
    """Reject IDs that would alter the URL path or query string.

    Args:
        value: The raw ID supplied by the caller.
        name: Parameter name (e.g. ``"page_id"``) — surfaced in the error
            so the caller knows which input was bad.

    Returns:
        The validated value, unchanged.

    Raises:
        ValidationError: Empty / whitespace-only IDs, and any ID containing
            characters that change URL semantics. Raised before the HTTP
            request is built so the bad value never leaves the process.
    """
    if not value or not value.strip():
        raise ValidationError(
            f"{name} cannot be empty",
            connector="notion",
            suggestion=(
                f"Pass a non-empty Notion UUID for {name}. "
                f"Example: '12345678-1234-1234-1234-123456789012'."
            ),
        )
    for bad in _FORBIDDEN_ID_CHARS:
        if bad in value:
            raise ValidationError(
                f"{name} contains forbidden character {bad!r}",
                connector="notion",
                suggestion=(
                    f"Notion IDs are UUIDs and must not contain '/', '?', "
                    f"or '#'. Got: {value!r}. If you pasted a URL by "
                    f"mistake, extract just the 32-char ID at the end."
                ),
                details={"forbidden_char": bad, "value": value},
            )
    return value


def _clamp_limit(limit: Optional[int], default: int = 100) -> int:
    """Clamp a paginated-action ``limit`` to Notion's accepted range.

    Notion accepts ``page_size`` in [1, 100]. Before this helper existed
    the code did only ``min(limit, 100)`` — which let ``limit=-5`` or
    ``limit=0`` leak to the API, wasting a round trip on a guaranteed
    400 response.

    Args:
        limit: The caller-supplied limit. May be ``None`` because the
            ToolKit / MCP dispatch layer passes ``None`` for optional
            params the caller omitted — bypassing the action method's
            own signature default. Coalesced to ``default`` in that case.
        default: Fallback used when ``limit is None``. Each action
            passes its own intended default here so the MCP path
            produces the same result as a direct Python call without
            an explicit limit.
    """
    if limit is None:
        limit = default
    return max(1, min(limit, 100))


# Notion error-code → actionable suggestion. Populates `e.suggestion` on
# every typed exception raised by this connector. The shared
# `raise_typed_for_status` helper handles the typed-class mapping; this
# table adds Notion-specific context on top.
_NOTION_CODE_SUGGESTIONS: dict[str, str] = {
    "unauthorized": (
        "Token may be invalid or revoked. Regenerate at https://www.notion.so/my-integrations."
    ),
    "restricted_resource": (
        "Integration is missing a required capability OR the target "
        "page/database is not shared with this integration. Fix at "
        "https://www.notion.so/my-integrations (capabilities) or open the "
        "page in Notion → '...' menu → 'Connections' → add your integration."
    ),
    "object_not_found": (
        "Object doesn't exist OR is not shared with this integration. "
        "Notion returns 404 for both cases. Open the page/database in "
        "Notion → '...' menu → 'Connections' → add your integration."
    ),
    "validation_error": (
        "Request body shape mismatch. Check property names, types, and "
        "database schema. See `details['notion_message']` for the specific "
        "field-level reason."
    ),
    "invalid_json": (
        "Request body is not valid JSON. This is a bug in the connector — please open an issue."
    ),
    "invalid_request_url": ("Internal: connector built an invalid URL. Please open an issue."),
    "missing_version": ("Internal: connector forgot Notion-Version header. Please open an issue."),
    "conflict_error": (
        "Concurrent edit conflict. Retry after fetching the latest version of the object."
    ),
    "rate_limited": (
        "Hit Notion's 3 req/s average limit. Wait per Retry-After header, "
        "then retry. Consider batching requests."
    ),
    "service_unavailable": (
        "Notion is unavailable or the request timed out (>60s). Retry with exponential backoff."
    ),
    "internal_server_error": (
        "Notion-side error. Retry with exponential backoff; if persistent, "
        "check https://status.notion.so."
    ),
    "database_connection_unavailable": (
        "Notion database connection unavailable. Retry with backoff."
    ),
    "gateway_timeout": ("Notion gateway timeout. Retry with backoff."),
}


class Notion(BaseConnector):
    """Connect to Notion to manage pages, databases, blocks, users, and comments.

    Uses the Notion REST API with internal-integration Bearer-token
    authentication (BYOK). Credentials should be a Notion integration
    token (string) — either the legacy ``secret_*`` format or the newer
    ``ntn_*`` format. OAuth flows are not handled by this connector;
    users bring their own token.

    **Prerequisite**: every page or database the integration should access
    must be explicitly shared with it via Notion's UI (open the page →
    ``...`` menu → ``Connections`` → add your integration). Pages NOT
    shared return 404, not 403 — the most common onboarding bug. The
    ``object_not_found`` error in ``e.details["notion_code"]`` and the
    ``e.suggestion`` field both call this out.

    **Capability profile**: integration tokens carry a capability profile
    set when the integration was created. Read content / Update content /
    Insert content / Read comments / Insert comments / Read user info are
    granted independently. Missing capabilities surface as
    ``PermissionDeniedError`` with ``e.details["notion_code"] ==
    "restricted_resource"``.

    See ``README.md`` for the full action reference, capability mapping,
    and verification status table.
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
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.request(
                    method,
                    url,
                    headers=self._headers(),
                    json=json,
                    params=params,
                )
        except httpx.TimeoutException as e:
            # ReadTimeout, ConnectTimeout, WriteTimeout, PoolTimeout — all
            # of these mean "the upstream did not respond within
            # ``self._timeout`` seconds". Map to our typed TimeoutError so
            # callers catching ToolsConnectorError see network slowness
            # rather than a bare httpx exception bleeding through.
            raise ToolsConnectorTimeoutError(
                f"Notion API request timed out after {self._timeout}s",
                connector=self.name,
                details={
                    "timeout_seconds": self._timeout,
                    "url": url,
                    "method": method,
                    "underlying": type(e).__name__,
                },
            ) from e
        except httpx.ConnectError as e:
            # DNS failure, TCP RST, TLS handshake failure, etc. — caller
            # should treat this as "transient, possibly retryable".
            raise ToolsConnectorConnectionError(
                f"Could not connect to Notion API at {self._base_url}",
                connector=self.name,
                details={"url": url, "underlying": str(e)},
            ) from e
        except httpx.TransportError as e:
            # Catch-all for any other transport-layer failure (ReadError,
            # WriteError, ProtocolError, etc.). httpx.HTTPError is the
            # broader root; httpx.TransportError covers the network/
            # socket subset that we want to surface as TransportError.
            raise TransportError(
                f"Notion API transport error: {type(e).__name__}",
                connector=self.name,
                details={"url": url, "underlying": str(e)},
            ) from e
        # NOTE: We deliberately don't catch httpx.HTTPError broadly —
        # that base class also covers things like InvalidURL which would
        # be a programmer bug, and we want those to surface unchanged.
        try:
            raise_typed_for_status(response, connector=self.name)
        except ToolsConnectorError as exc:
            # Augment with Notion's structured error code + suggestion.
            # The typed-class mapping (401→InvalidCredentialsError,
            # 403→PermissionDeniedError, etc.) is owned by the shared
            # helper; this just attaches Notion-specific context.
            try:
                body = response.json()
            except ValueError:
                body = None
            if isinstance(body, dict) and body.get("object") == "error":
                code = body.get("code")
                exc.details["notion_code"] = code
                exc.details["notion_message"] = body.get("message")
                if isinstance(code, str) and code in _NOTION_CODE_SUGGESTIONS:
                    exc.suggestion = _NOTION_CODE_SUGGESTIONS[code]
            raise
        # 204 No Content (DELETE) and empty 200 bodies both return
        # an empty dict so callers that expect to call .get() don't
        # crash. Notion's DELETE /comments/{id} returns 204; other
        # actions never return empty bodies under normal operation.
        if not response.content:
            return {}
        parsed = response.json()
        # Defensive: if Notion ever returns JSON `null` as the body,
        # response.json() yields None. Treat that the same as empty
        # so downstream `data.get(...)` calls don't AttributeError.
        if parsed is None:
            return {}
        return parsed

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
        body: dict[str, Any] = {"query": query, "page_size": _clamp_limit(limit, default=20)}
        if filter_type:
            body["filter"] = {"value": filter_type, "property": "object"}
        if cursor:
            body["start_cursor"] = cursor

        data = await self._request("POST", "/search", json=body)

        # Notion's /search returns mixed pages + databases. The action's
        # declared return type is PaginatedList[NotionPage], so we
        # enforce that contract here by filtering to results whose
        # ``object == "page"``. Callers who want databases should pass
        # ``filter_type="database"`` (which returns database objects
        # the server-side filter ensures we never see here) and inspect
        # via a separate code path — or use `query_database` directly.
        # Server-side filtering is best-effort; this filter is the
        # defensive guard against an unfiltered search.
        page_results = [r for r in data.get("results", []) if r.get("object") == "page"]
        pages = [parse_page(r) for r in page_results]
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
        _validate_id(page_id, "page_id")
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
        _validate_id(parent_id, "parent_id")
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
        _validate_id(page_id, "page_id")
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
        _validate_id(database_id, "database_id")
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
        _validate_id(database_id, "database_id")
        body: dict[str, Any] = {"page_size": _clamp_limit(limit, default=50)}
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
        _validate_id(parent_id, "parent_id")
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
        _validate_id(block_id, "block_id")
        params: dict[str, Any] = {"page_size": _clamp_limit(limit, default=50)}
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
        _validate_id(block_id, "block_id")
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
        _validate_id(block_id, "block_id")
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
        _validate_id(block_id, "block_id")
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
        users: list[NotionUser] = []
        for u in data.get("results", []):
            parsed = parse_user(u)
            if parsed is not None:
                users.append(parsed)
        return users

    @action("Get a single user by ID")
    async def get_user(self, user_id: str) -> NotionUser:
        """Retrieve a single workspace user by their ID.

        Args:
            user_id: UUID of the user to retrieve.

        Returns:
            The requested NotionUser.
        """
        _validate_id(user_id, "user_id")
        data = await self._request("GET", f"/users/{user_id}")
        parsed = parse_user(data)
        # /users/{id} returns a single user object — by contract, never
        # null. parse_user only returns None when fed an empty/None dict.
        assert parsed is not None, "Notion /users/{id} returned no user object"
        return parsed

    @action("Get the bot user associated with the integration token")
    async def get_me(self) -> NotionUser:
        """Retrieve the bot user that owns the current integration token.

        Useful for agents that need to identify themselves — the bot
        user's UUID can then be referenced in ``people`` properties or
        ``created_by`` filters. Returns the bot user, NOT the workspace
        owner.

        Returns:
            The integration's bot NotionUser.
        """
        data = await self._request("GET", "/users/me")
        parsed = parse_user(data)
        assert parsed is not None, "Notion /users/me returned no user object"
        return parsed

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
        _validate_id(block_id, "block_id")
        params: dict[str, Any] = {
            "block_id": block_id,
            "page_size": _clamp_limit(limit, default=50),
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

    @action("Add a comment to a page or discussion thread", dangerous=True)
    async def add_comment(
        self,
        page_id: str,
        text: str,
        discussion_id: Optional[str] = None,
    ) -> NotionComment:
        """Add a new comment, either as a top-level page comment or a reply.

        When ``discussion_id`` is ``None`` (default), creates a new top-level
        comment on ``page_id``. When ``discussion_id`` is provided, the
        comment is appended to that existing thread (``page_id`` is ignored
        in that case, per Notion's API — the thread already knows its
        page). Once a thread is started, every reply must use the same
        ``discussion_id``.

        Args:
            page_id: UUID of the page to comment on. Used only when
                ``discussion_id`` is None.
            text: Plain-text content of the comment.
            discussion_id: Optional UUID of an existing discussion thread.
                When set, the comment is added to that thread.

        Returns:
            The newly created NotionComment. Its ``discussion_id`` field
            can be reused to thread further replies.
        """
        body: dict[str, Any]
        if discussion_id is not None:
            # Threaded reply: Notion's 2022-06-28 API expects
            # ``discussion_id`` at the TOP LEVEL of the body — NOT nested
            # under ``parent``. This asymmetry vs the page-id form caught
            # us once already; the live test against the real Notion API
            # returns HTTP 400 with code `validation_error` if the field
            # is wrapped in ``{"parent": {"discussion_id": ...}}``.
            _validate_id(discussion_id, "discussion_id")
            body = {
                "discussion_id": discussion_id,
                "rich_text": [{"text": {"content": text}}],
            }
        else:
            # Top-level page comment: parent goes through the standard
            # ``{"parent": {"page_id": ...}}`` envelope.
            _validate_id(page_id, "page_id")
            body = {
                "parent": {"page_id": page_id},
                "rich_text": [{"text": {"content": text}}],
            }
        data = await self._request("POST", "/comments", json=body)
        return parse_comment(data)

    @action("Get a single comment by ID")
    async def get_comment(self, comment_id: str) -> NotionComment:
        """Retrieve a single Notion comment by its ID.

        Args:
            comment_id: UUID of the comment to retrieve.

        Returns:
            The requested NotionComment.
        """
        _validate_id(comment_id, "comment_id")
        data = await self._request("GET", f"/comments/{comment_id}")
        return parse_comment(data)

    @action("Update a comment's text")
    async def update_comment(
        self,
        comment_id: str,
        text: str,
    ) -> NotionComment:
        """Replace the rich-text content of an existing comment.

        Args:
            comment_id: UUID of the comment to update.
            text: New plain-text content for the comment.

        Returns:
            The updated NotionComment.
        """
        body: dict[str, Any] = {
            "rich_text": [{"text": {"content": text}}],
        }
        _validate_id(comment_id, "comment_id")
        data = await self._request("PATCH", f"/comments/{comment_id}", json=body)
        return parse_comment(data)

    @action("Delete a comment", dangerous=True)
    async def delete_comment(self, comment_id: str) -> None:
        """Delete a comment by its ID.

        This is a destructive action — the comment is removed from its
        thread permanently.

        Args:
            comment_id: UUID of the comment to delete.
        """
        _validate_id(comment_id, "comment_id")
        await self._request("DELETE", f"/comments/{comment_id}")

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

        _validate_id(database_id, "database_id")
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
        _validate_id(page_id, "page_id")
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
        _validate_id(page_id, "page_id")
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
        _validate_id(block_id, "block_id")
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
        cursor: Optional[str] = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Retrieve a specific property value from a Notion page.

        This endpoint is the only way to read complete values for
        paginated property types — ``title``, ``rich_text``, ``relation``,
        ``rollup``, and ``people`` — because the page object itself
        truncates these to 25 references.

        Response shape varies by property type:

        - **Non-paginated** (number, checkbox, date, select, etc.) — returns
          a single property-item object: ``{"object": "property_item",
          "type": "<type>", "<type>": <value>, "id": "<prop_id>"}``.

        - **Paginated** (title, rich_text, relation, rollup, people) — returns
          a list wrapper: ``{"object": "list", "type": "property_item",
          "results": [...], "has_more": bool, "next_cursor": <str|null>,
          "property_item": {"id": "<prop_id>", "type": "<type>",
          "next_url": "..."}}``. If ``has_more`` is True, pass
          ``next_cursor`` back as ``cursor`` to fetch the next page.

        Args:
            page_id: UUID of the page.
            property_id: The ID of the property to retrieve (found in
                the page's ``properties`` dict under each property's
                ``id`` field).
            cursor: For paginated property types, pass the ``next_cursor``
                from a previous response to retrieve the next page.
            limit: Items per page for paginated property types
                (max 100; clamped if higher).

        Returns:
            Raw property value dict from the Notion API. Inspect the
            ``object`` field to distinguish paginated (``"list"``) from
            single-value (``"property_item"``) responses.
        """
        _validate_id(page_id, "page_id")
        _validate_id(property_id, "property_id")
        params: dict[str, Any] = {"page_size": _clamp_limit(limit, default=100)}
        if cursor:
            params["start_cursor"] = cursor
        data = await self._request(
            "GET",
            f"/pages/{page_id}/properties/{property_id}",
            params=params,
        )
        return data
