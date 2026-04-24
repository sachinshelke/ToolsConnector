"""Segment connector -- track, identify, page, group, alias, and source management.

Uses httpx for direct HTTP calls against the Segment APIs.
The tracking API (track, identify, page, group, alias) uses Basic auth
with the write key as the username and an empty password.
The config API (sources, destinations) uses Bearer token authentication.

Credentials format: ``write_key:api_token`` (colon-separated).
The write_key is used for the tracking API, the api_token for the config API.
If only a write_key is provided, config API actions will not be available.
"""

from __future__ import annotations

import base64
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

from .types import (
    SegmentDestination,
    SegmentSource,
    SegmentTrackResult,
)

logger = logging.getLogger("toolsconnector.segment")

_TRACKING_URL = "https://api.segment.io/v1"
_CONFIG_URL = "https://api.segmentapis.com"


class Segment(BaseConnector):
    """Connect to Segment for event tracking and source/destination management.

    Supports dual authentication:
    - Tracking API: Basic auth with write key as username (empty password).
    - Config API: Bearer token for managing sources and destinations.

    Pass credentials as ``write_key:api_token`` (colon-separated).
    If only tracking is needed, pass just the write key.
    """

    name = "segment"
    display_name = "Segment"
    category = ConnectorCategory.ANALYTICS
    protocol = ProtocolType.REST
    base_url = "https://api.segment.io/v1"
    description = (
        "Connect to Segment for event tracking (track, identify, page, group, alias) "
        "and source/destination management via the Config API."
    )
    _rate_limit_config = RateLimitSpec(rate=250, period=60, burst=50)

    # ------------------------------------------------------------------
    # Credential parsing
    # ------------------------------------------------------------------

    def _parse_credentials(self) -> tuple[str, Optional[str]]:
        """Parse write_key and api_token from the credentials string.

        Returns:
            Tuple of (write_key, api_token). api_token may be None.
        """
        creds = str(self._credentials)
        if ":" in creds:
            parts = creds.split(":", 1)
            return parts[0], parts[1] if parts[1] else None
        return creds, None

    @property
    def _write_key(self) -> str:
        """Return the Segment write key."""
        return self._parse_credentials()[0]

    @property
    def _api_token(self) -> Optional[str]:
        """Return the Segment Config API token, if available."""
        return self._parse_credentials()[1]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_tracking_headers(self) -> dict[str, str]:
        """Build auth headers for Segment tracking API requests.

        Uses Basic auth with write key as username and empty password.

        Returns:
            Dict with Authorization header and content type.
        """
        encoded = base64.b64encode(f"{self._write_key}:".encode()).decode("ascii")
        return {
            "Authorization": f"Basic {encoded}",
            "Content-Type": "application/json",
        }

    def _get_config_headers(self) -> dict[str, str]:
        """Build auth headers for Segment Config API requests.

        Uses Bearer token authentication.

        Returns:
            Dict with Authorization header and content type.
        """
        return {
            "Authorization": f"Bearer {self._api_token}",
            "Content-Type": "application/json",
        }

    async def _tracking_request(
        self,
        path: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute an authenticated request against the Segment tracking API.

        Args:
            path: API path (e.g., '/track', '/identify').
            payload: JSON payload for the request.

        Returns:
            Parsed JSON response as a dict.

        Raises:
            toolsconnector.errors.APIError (subclass): On any non-2xx response.
                Maps to a typed exception by status: 401 -> InvalidCredentialsError
                or TokenExpiredError; 403 -> PermissionDeniedError; 404 -> NotFoundError;
                409 -> ConflictError; 400/422 -> ValidationError; 429 -> RateLimitError;
                5xx -> ServerError; other 4xx -> APIError. See
                toolsconnector.connectors._helpers.raise_typed_for_status for the full mapping.

        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{_TRACKING_URL}{path}",
                headers=self._get_tracking_headers(),
                json=payload,
            )
            raise_typed_for_status(response, connector=self.name)
            if response.status_code == 204 or not response.content:
                return {"success": True}
            return response.json()

    async def _config_request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute an authenticated request against the Segment Config API.

        Args:
            method: HTTP method (GET, POST, etc.).
            path: API path (e.g., '/sources').
            **kwargs: Additional keyword arguments passed to httpx.

        Returns:
            Parsed JSON response as a dict.

        Raises:
            toolsconnector.errors.APIError (subclass): On any non-2xx response.
                Maps to a typed exception by status: 401 -> InvalidCredentialsError
                or TokenExpiredError; 403 -> PermissionDeniedError; 404 -> NotFoundError;
                409 -> ConflictError; 400/422 -> ValidationError; 429 -> RateLimitError;
                5xx -> ServerError; other 4xx -> APIError. See
                toolsconnector.connectors._helpers.raise_typed_for_status for the full mapping.

        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.request(
                method,
                f"{_CONFIG_URL}{path}",
                headers=self._get_config_headers(),
                **kwargs,
            )
            raise_typed_for_status(response, connector=self.name)
            if response.status_code == 204 or not response.content:
                return {}
            return response.json()

    # ------------------------------------------------------------------
    # Tracking Actions
    # ------------------------------------------------------------------

    @action("Track an event for a user")
    async def track(
        self,
        user_id: str,
        event: str,
        properties: Optional[dict[str, Any]] = None,
    ) -> SegmentTrackResult:
        """Track an event performed by a user.

        Args:
            user_id: Unique identifier for the user.
            event: Name of the event to track.
            properties: Properties associated with the event.

        Returns:
            SegmentTrackResult indicating success.
        """
        payload: dict[str, Any] = {
            "userId": user_id,
            "event": event,
        }
        if properties is not None:
            payload["properties"] = properties

        data = await self._tracking_request("/track", payload)
        return SegmentTrackResult(
            success=data.get("success", True),
            message=data.get("message"),
        )

    @action("Identify a user with traits")
    async def identify(
        self,
        user_id: str,
        traits: Optional[dict[str, Any]] = None,
    ) -> SegmentTrackResult:
        """Identify a user with specific traits.

        Associates traits (name, email, plan, etc.) with a specific
        user so all future events are enriched with that context.

        Args:
            user_id: Unique identifier for the user.
            traits: User traits such as name, email, plan, etc.

        Returns:
            SegmentTrackResult indicating success.
        """
        payload: dict[str, Any] = {"userId": user_id}
        if traits is not None:
            payload["traits"] = traits

        data = await self._tracking_request("/identify", payload)
        return SegmentTrackResult(
            success=data.get("success", True),
            message=data.get("message"),
        )

    @action("Track a page view")
    async def page(
        self,
        user_id: str,
        name: Optional[str] = None,
        properties: Optional[dict[str, Any]] = None,
    ) -> SegmentTrackResult:
        """Track a page view for a user.

        Args:
            user_id: Unique identifier for the user.
            name: Name of the page being viewed.
            properties: Additional properties for the page view.

        Returns:
            SegmentTrackResult indicating success.
        """
        payload: dict[str, Any] = {"userId": user_id}
        if name is not None:
            payload["name"] = name
        if properties is not None:
            payload["properties"] = properties

        data = await self._tracking_request("/page", payload)
        return SegmentTrackResult(
            success=data.get("success", True),
            message=data.get("message"),
        )

    @action("Associate a user with a group")
    async def group(
        self,
        user_id: str,
        group_id: str,
        traits: Optional[dict[str, Any]] = None,
    ) -> SegmentTrackResult:
        """Associate a user with a group (company, team, account).

        Args:
            user_id: Unique identifier for the user.
            group_id: Unique identifier for the group.
            traits: Group traits such as name, industry, employees, etc.

        Returns:
            SegmentTrackResult indicating success.
        """
        payload: dict[str, Any] = {
            "userId": user_id,
            "groupId": group_id,
        }
        if traits is not None:
            payload["traits"] = traits

        data = await self._tracking_request("/group", payload)
        return SegmentTrackResult(
            success=data.get("success", True),
            message=data.get("message"),
        )

    @action("Create an alias for a user")
    async def alias(
        self,
        previous_id: str,
        user_id: str,
    ) -> SegmentTrackResult:
        """Create an alias linking a previous ID to a new user ID.

        Merges two user identities together, typically used when
        an anonymous user signs up and gets a permanent user ID.

        Args:
            previous_id: The previous (anonymous) user identifier.
            user_id: The new canonical user identifier.

        Returns:
            SegmentTrackResult indicating success.
        """
        payload: dict[str, Any] = {
            "previousId": previous_id,
            "userId": user_id,
        }

        data = await self._tracking_request("/alias", payload)
        return SegmentTrackResult(
            success=data.get("success", True),
            message=data.get("message"),
        )

    # ------------------------------------------------------------------
    # Config API Actions
    # ------------------------------------------------------------------

    @action("List sources in the workspace", idempotent=True)
    async def list_sources(
        self,
        limit: Optional[int] = None,
    ) -> PaginatedList[SegmentSource]:
        """List all sources in the Segment workspace.

        Requires a Config API token in the credentials.

        Args:
            limit: Maximum number of sources to return.

        Returns:
            Paginated list of SegmentSource objects.
        """
        params: dict[str, Any] = {}
        if limit is not None:
            params["pagination.count"] = limit

        data = await self._config_request("GET", "/sources", params=params)

        sources = [
            SegmentSource(
                id=s.get("id", ""),
                slug=s.get("slug", ""),
                name=s.get("name", ""),
                workspace_id=s.get("workspaceId", ""),
                enabled=s.get("enabled", True),
                write_keys=s.get("writeKeys", []),
                metadata=s.get("metadata"),
                settings=s.get("settings"),
                labels=s.get("labels", []),
            )
            for s in data.get("data", {}).get("sources", [])
        ]

        pagination = data.get("data", {}).get("pagination", {})
        next_cursor = pagination.get("next")

        return PaginatedList(
            items=sources,
            page_state=PageState(
                cursor=next_cursor,
                has_more=next_cursor is not None,
            ),
            total_count=pagination.get("totalEntries"),
        )

    @action("Get a specific source by ID", idempotent=True)
    async def get_source(
        self,
        source_id: str,
    ) -> SegmentSource:
        """Get details for a specific Segment source.

        Requires a Config API token in the credentials.

        Args:
            source_id: The unique identifier of the source.

        Returns:
            SegmentSource with full source details.
        """
        data = await self._config_request("GET", f"/sources/{source_id}")

        s = data.get("data", {}).get("source", {})
        return SegmentSource(
            id=s.get("id", ""),
            slug=s.get("slug", ""),
            name=s.get("name", ""),
            workspace_id=s.get("workspaceId", ""),
            enabled=s.get("enabled", True),
            write_keys=s.get("writeKeys", []),
            metadata=s.get("metadata"),
            settings=s.get("settings"),
            labels=s.get("labels", []),
        )

    @action("List destinations for a source", idempotent=True)
    async def list_destinations(
        self,
        source_id: str,
    ) -> list[SegmentDestination]:
        """List all destinations connected to a specific source.

        Requires a Config API token in the credentials.

        Args:
            source_id: The unique identifier of the source.

        Returns:
            List of SegmentDestination objects.
        """
        data = await self._config_request(
            "GET",
            f"/sources/{source_id}/destinations",
        )

        return [
            SegmentDestination(
                id=d.get("id", ""),
                name=d.get("name", ""),
                enabled=d.get("enabled", True),
                source_id=d.get("sourceId", source_id),
                connection_mode=d.get("connectionMode", ""),
                metadata=d.get("metadata"),
                settings=d.get("settings"),
            )
            for d in data.get("data", {}).get("destinations", [])
        ]

    # ------------------------------------------------------------------
    # Actions -- Source management (extended)
    # ------------------------------------------------------------------

    @action("Create a new Segment source", dangerous=True)
    async def create_source(
        self,
        name: str,
        catalog_name: str,
    ) -> SegmentSource:
        """Create a new Segment source.

        Args:
            name: Display name for the source.
            catalog_name: Catalog name (e.g. ``"catalog/sources/javascript"``).

        Returns:
            The created SegmentSource.
        """
        payload: dict[str, Any] = {
            "source": {
                "name": name,
                "catalog_name": catalog_name,
            },
        }
        resp = await self._config_request(
            "POST",
            "/sources",
            json_body=payload,
        )
        data = resp.json()
        s = data.get("data", {}).get("source", {})
        return SegmentSource(
            id=s.get("id", ""),
            name=s.get("name", ""),
            slug=s.get("slug"),
            catalog_name=s.get("catalog_name"),
            workspace_id=s.get("workspace_id"),
            enabled=s.get("enabled", True),
            write_keys=s.get("write_keys", []),
            metadata=s.get("metadata"),
            created_at=s.get("created_at"),
        )

    @action("Delete a Segment source", dangerous=True)
    async def delete_source(self, source_id: str) -> bool:
        """Delete a Segment source.

        Args:
            source_id: The source ID.

        Returns:
            True if the source was deleted.
        """
        resp = await self._config_request(
            "DELETE",
            f"/sources/{source_id}",
        )
        return resp.status_code in (200, 204)

    # ------------------------------------------------------------------
    # Actions -- Warehouses
    # ------------------------------------------------------------------

    @action("List connected warehouses")
    async def list_warehouses(self) -> list[dict[str, Any]]:
        """List all connected warehouses in the workspace.

        Returns:
            List of warehouse configuration dicts.
        """
        resp = await self._config_request("GET", "/warehouses")
        data = resp.json()
        return data.get("data", {}).get("warehouses", [])

    # ------------------------------------------------------------------
    # Actions -- Destination details
    # ------------------------------------------------------------------

    @action("Get a specific destination for a source", idempotent=True)
    async def get_destination(
        self,
        source_id: str,
        destination_id: str,
    ) -> SegmentDestination:
        """Get details for a specific destination connected to a source.

        Requires a Config API token in the credentials.

        Args:
            source_id: The source ID.
            destination_id: The destination ID.

        Returns:
            SegmentDestination with full details.
        """
        data = await self._config_request(
            "GET",
            f"/sources/{source_id}/destinations/{destination_id}",
        )
        d = data.get("data", {}).get("destination", data)
        return SegmentDestination(
            id=d.get("id", ""),
            name=d.get("name", ""),
            enabled=d.get("enabled", True),
            source_id=d.get("sourceId", source_id),
            connection_mode=d.get("connectionMode", ""),
            metadata=d.get("metadata"),
            settings=d.get("settings"),
        )

    # ------------------------------------------------------------------
    # Actions -- Batch tracking
    # ------------------------------------------------------------------

    @action("Send a batch of track events", dangerous=True)
    async def batch_track(
        self,
        events: list[dict[str, Any]],
    ) -> SegmentTrackResult:
        """Send multiple track events in a single batch request.

        Each event dict should contain ``userId``, ``event``, and
        optionally ``properties`` and ``timestamp``.

        Args:
            events: List of event dicts to track.

        Returns:
            SegmentTrackResult indicating batch success.
        """
        payload: dict[str, Any] = {"batch": events}
        data = await self._tracking_request("/batch", payload)
        return SegmentTrackResult(
            success=data.get("success", True),
            message=data.get("message"),
        )

    @action("Send a batch of identify calls", dangerous=True)
    async def batch_identify(
        self,
        users: list[dict[str, Any]],
    ) -> SegmentTrackResult:
        """Send multiple identify calls in a single batch request.

        Each user dict should contain ``userId`` and optionally
        ``traits`` and ``timestamp``. The ``type`` field is
        automatically set to ``identify``.

        Args:
            users: List of user dicts to identify.

        Returns:
            SegmentTrackResult indicating batch success.
        """
        batch = [{**u, "type": "identify"} for u in users]
        payload: dict[str, Any] = {"batch": batch}
        data = await self._tracking_request("/batch", payload)
        return SegmentTrackResult(
            success=data.get("success", True),
            message=data.get("message"),
        )
