"""PagerDuty connector -- incidents, services, on-calls, and users.

Uses the PagerDuty REST API v2 with token-based authentication.
Supports offset-based pagination via ``offset`` and ``more`` response fields.
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

from .types import PDIncident, PDOncall, PDService, PDUser

logger = logging.getLogger("toolsconnector.pagerduty")


def _parse_service(data: dict[str, Any]) -> PDService:
    """Parse a PDService from API JSON.

    Args:
        data: Raw JSON dict from the PagerDuty API.

    Returns:
        A PDService instance.
    """
    return PDService(
        id=data.get("id"),
        name=data.get("name"),
        description=data.get("description"),
        status=data.get("status"),
        html_url=data.get("html_url"),
        summary=data.get("summary"),
        type=data.get("type", "service"),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
        escalation_policy=data.get("escalation_policy"),
        teams=data.get("teams") or [],
        alert_creation=data.get("alert_creation"),
    )


def _parse_user(data: dict[str, Any]) -> PDUser:
    """Parse a PDUser from API JSON.

    Args:
        data: Raw JSON dict from the PagerDuty API.

    Returns:
        A PDUser instance.
    """
    return PDUser(
        id=data.get("id"),
        type=data.get("type", "user"),
        name=data.get("name"),
        email=data.get("email"),
        html_url=data.get("html_url"),
        summary=data.get("summary"),
        time_zone=data.get("time_zone"),
        role=data.get("role"),
        avatar_url=data.get("avatar_url"),
    )


def _parse_incident(data: dict[str, Any]) -> PDIncident:
    """Parse a PDIncident from API JSON.

    Args:
        data: Raw JSON dict from the PagerDuty API.

    Returns:
        A PDIncident instance.
    """
    service_data = data.get("service")
    service = _parse_service(service_data) if service_data else None

    return PDIncident(
        id=data.get("id"),
        type=data.get("type", "incident"),
        title=data.get("title"),
        description=data.get("description"),
        status=data.get("status"),
        urgency=data.get("urgency"),
        html_url=data.get("html_url"),
        summary=data.get("summary"),
        incident_number=data.get("incident_number"),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
        last_status_change_at=data.get("last_status_change_at"),
        service=service,
        assignments=data.get("assignments") or [],
        assigned_via=data.get("assigned_via"),
        escalation_policy=data.get("escalation_policy"),
        teams=data.get("teams") or [],
        acknowledgements=data.get("acknowledgements") or [],
        alert_counts=data.get("alert_counts"),
    )


def _parse_oncall(data: dict[str, Any]) -> PDOncall:
    """Parse a PDOncall from API JSON.

    Args:
        data: Raw JSON dict from the PagerDuty API.

    Returns:
        A PDOncall instance.
    """
    user_data = data.get("user")
    user = _parse_user(user_data) if user_data else None

    return PDOncall(
        user=user,
        schedule=data.get("schedule"),
        escalation_policy=data.get("escalation_policy"),
        escalation_level=data.get("escalation_level"),
        start=data.get("start"),
        end=data.get("end"),
    )


class PagerDuty(BaseConnector):
    """Connect to PagerDuty to manage incidents, services, and on-calls.

    Authenticates via PagerDuty REST API token using the
    ``Authorization: Token token={api_key}`` header format.
    """

    name = "pagerduty"
    display_name = "PagerDuty"
    category = ConnectorCategory.DEVOPS
    protocol = ProtocolType.REST
    base_url = "https://api.pagerduty.com"
    description = (
        "Connect to PagerDuty to manage incidents, list services, "
        "view on-call schedules, and acknowledge incidents."
    )
    _rate_limit_config = RateLimitSpec(rate=960, period=60, burst=50)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Initialise the httpx async client with PagerDuty auth."""
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/vnd.pagerduty+json;version=2",
        }
        if self._credentials:
            headers["Authorization"] = f"Token token={self._credentials}"

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
        json: Optional[dict[str, Any]] = None,
    ) -> httpx.Response:
        """Send an authenticated request to the PagerDuty API.

        Args:
            method: HTTP method (GET, POST, PUT).
            path: API path relative to base_url.
            params: Query parameters.
            json: JSON body for POST/PUT requests.

        Returns:
            httpx.Response object.

        Raises:
            httpx.HTTPStatusError: On 4xx/5xx responses.
        """
        resp = await self._client.request(
            method, path, params=params, json=json,
        )
        resp.raise_for_status()
        return resp

    def _build_page_state(
        self, body: dict[str, Any], offset: int, limit: int,
    ) -> PageState:
        """Build a PageState from PagerDuty offset pagination.

        Args:
            body: The response body dict.
            offset: Current offset value.
            limit: Current page size.

        Returns:
            PageState with cursor set to next offset if more data exists.
        """
        has_more = body.get("more", False)
        next_offset = str(offset + limit) if has_more else None
        return PageState(has_more=has_more, cursor=next_offset)

    # ------------------------------------------------------------------
    # Actions -- Incidents
    # ------------------------------------------------------------------

    @action("List PagerDuty incidents")
    async def list_incidents(
        self,
        status: Optional[str] = None,
        limit: int = 25,
        page: Optional[str] = None,
    ) -> PaginatedList[PDIncident]:
        """List incidents from the PagerDuty account.

        Args:
            status: Filter by status (``triggered``, ``acknowledged``,
                ``resolved``). Comma-separate for multiple.
            limit: Maximum incidents per page (max 100).
            page: Cursor (offset string) for the next page.

        Returns:
            Paginated list of PDIncident objects.
        """
        offset = int(page) if page else 0
        capped_limit = min(limit, 100)
        params: dict[str, Any] = {"limit": capped_limit, "offset": offset}
        if status:
            params["statuses[]"] = status.split(",")

        resp = await self._request("GET", "/incidents", params=params)
        body = resp.json()
        items = [_parse_incident(i) for i in body.get("incidents", [])]
        ps = self._build_page_state(body, offset, capped_limit)

        result = PaginatedList(items=items, page_state=ps)
        if ps.has_more:
            result._fetch_next = lambda c=ps.cursor: self.list_incidents(
                status=status, limit=capped_limit, page=c,
            )
        return result

    @action("Get a single PagerDuty incident by ID")
    async def get_incident(self, incident_id: str) -> PDIncident:
        """Retrieve a single incident by its ID.

        Args:
            incident_id: The PagerDuty incident ID.

        Returns:
            PDIncident object.
        """
        resp = await self._request("GET", f"/incidents/{incident_id}")
        return _parse_incident(resp.json().get("incident", {}))

    @action("Create a PagerDuty incident", dangerous=True)
    async def create_incident(
        self,
        service_id: str,
        title: str,
        body: Optional[str] = None,
        urgency: Optional[str] = None,
    ) -> PDIncident:
        """Create a new incident in PagerDuty.

        Args:
            service_id: The ID of the service to create the incident on.
            title: Incident title.
            body: Incident body text with details.
            urgency: Urgency level (``high`` or ``low``).

        Returns:
            The created PDIncident object.
        """
        incident_data: dict[str, Any] = {
            "type": "incident",
            "title": title,
            "service": {
                "id": service_id,
                "type": "service_reference",
            },
        }
        if body is not None:
            incident_data["body"] = {
                "type": "incident_body",
                "details": body,
            }
        if urgency is not None:
            incident_data["urgency"] = urgency

        payload: dict[str, Any] = {"incident": incident_data}
        resp = await self._request("POST", "/incidents", json=payload)
        return _parse_incident(resp.json().get("incident", {}))

    @action("Update a PagerDuty incident status", dangerous=True)
    async def update_incident(
        self, incident_id: str, status: str,
    ) -> PDIncident:
        """Update an incident's status.

        Args:
            incident_id: The PagerDuty incident ID.
            status: New status (``acknowledged`` or ``resolved``).

        Returns:
            The updated PDIncident object.
        """
        payload: dict[str, Any] = {
            "incident": {
                "type": "incident_reference",
                "status": status,
            },
        }
        resp = await self._request(
            "PUT", f"/incidents/{incident_id}", json=payload,
        )
        return _parse_incident(resp.json().get("incident", {}))

    @action("Acknowledge a PagerDuty incident", dangerous=True)
    async def acknowledge_incident(
        self, incident_id: str,
    ) -> PDIncident:
        """Acknowledge an incident (shorthand for updating status).

        Args:
            incident_id: The PagerDuty incident ID to acknowledge.

        Returns:
            The acknowledged PDIncident object.
        """
        return await self.update_incident(incident_id, "acknowledged")

    # ------------------------------------------------------------------
    # Actions -- Services
    # ------------------------------------------------------------------

    @action("List PagerDuty services")
    async def list_services(
        self,
        limit: int = 25,
        page: Optional[str] = None,
    ) -> PaginatedList[PDService]:
        """List services configured in PagerDuty.

        Args:
            limit: Maximum services per page (max 100).
            page: Cursor (offset string) for the next page.

        Returns:
            Paginated list of PDService objects.
        """
        offset = int(page) if page else 0
        capped_limit = min(limit, 100)
        params: dict[str, Any] = {"limit": capped_limit, "offset": offset}

        resp = await self._request("GET", "/services", params=params)
        body = resp.json()
        items = [_parse_service(s) for s in body.get("services", [])]
        ps = self._build_page_state(body, offset, capped_limit)

        result = PaginatedList(items=items, page_state=ps)
        if ps.has_more:
            result._fetch_next = lambda c=ps.cursor: self.list_services(
                limit=capped_limit, page=c,
            )
        return result

    @action("Get a single PagerDuty service by ID")
    async def get_service(self, service_id: str) -> PDService:
        """Retrieve a single service by its ID.

        Args:
            service_id: The PagerDuty service ID.

        Returns:
            PDService object.
        """
        resp = await self._request("GET", f"/services/{service_id}")
        return _parse_service(resp.json().get("service", {}))

    # ------------------------------------------------------------------
    # Actions -- On-Calls
    # ------------------------------------------------------------------

    @action("List PagerDuty on-call entries")
    async def list_oncalls(
        self,
        schedule_id: Optional[str] = None,
    ) -> PaginatedList[PDOncall]:
        """List current on-call entries across schedules.

        Args:
            schedule_id: Filter to a specific schedule ID.

        Returns:
            Paginated list of PDOncall objects.
        """
        params: dict[str, Any] = {}
        if schedule_id:
            params["schedule_ids[]"] = schedule_id

        resp = await self._request("GET", "/oncalls", params=params)
        body = resp.json()
        items = [_parse_oncall(o) for o in body.get("oncalls", [])]
        return PaginatedList(
            items=items,
            page_state=PageState(has_more=False),
        )

    # ------------------------------------------------------------------
    # Actions -- Incident management (extended)
    # ------------------------------------------------------------------

    @action("Resolve an incident")
    async def resolve_incident(
        self, incident_id: str,
    ) -> PDIncident:
        """Resolve a PagerDuty incident.

        Args:
            incident_id: The incident ID.

        Returns:
            The resolved PDIncident.
        """
        payload: dict[str, Any] = {
            "incident": {
                "type": "incident_reference",
                "status": "resolved",
            },
        }
        resp = await self._request(
            "PUT", f"/incidents/{incident_id}", json_body=payload,
        )
        data = resp.json()
        return _parse_incident(data.get("incident", {}))

    @action("Add a note to an incident")
    async def add_note(
        self, incident_id: str, content: str,
    ) -> dict[str, Any]:
        """Add a note to a PagerDuty incident.

        Args:
            incident_id: The incident ID.
            content: The note content text.

        Returns:
            Dict with the created note details.
        """
        payload: dict[str, Any] = {
            "note": {"content": content},
        }
        resp = await self._request(
            "POST", f"/incidents/{incident_id}/notes", json_body=payload,
        )
        return resp.json().get("note", {})

    # ------------------------------------------------------------------
    # Actions -- Users
    # ------------------------------------------------------------------

    @action("List PagerDuty users")
    async def list_users(
        self, limit: Optional[int] = None,
    ) -> list[PDUser]:
        """List users in the PagerDuty account.

        Args:
            limit: Maximum number of users to return.

        Returns:
            List of PDUser objects.
        """
        params: dict[str, Any] = {}
        if limit is not None:
            params["limit"] = min(limit, 100)
        resp = await self._request(
            "GET", "/users", params=params or None,
        )
        body = resp.json()
        return [_parse_user(u) for u in body.get("users", [])]

    # ------------------------------------------------------------------
    # Actions -- Services
    # ------------------------------------------------------------------

    @action("Create a new PagerDuty service", dangerous=True)
    async def create_service(
        self,
        name: str,
        escalation_policy_id: str,
    ) -> PDService:
        """Create a new PagerDuty service.

        Args:
            name: Service name.
            escalation_policy_id: ID of the escalation policy.

        Returns:
            The created PDService.
        """
        payload: dict[str, Any] = {
            "service": {
                "type": "service",
                "name": name,
                "escalation_policy": {
                    "id": escalation_policy_id,
                    "type": "escalation_policy_reference",
                },
            },
        }
        resp = await self._request(
            "POST", "/services", json_body=payload,
        )
        return _parse_service(resp.json().get("service", {}))
