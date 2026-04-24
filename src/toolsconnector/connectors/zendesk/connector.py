"""Zendesk connector -- tickets, users, comments, and search.

Uses the Zendesk REST API v2 with Basic auth (email/token:api_token).
Cursor-based pagination via ``after_cursor`` for list endpoints.
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

from ._parsers import parse_search_result, parse_ticket, parse_user
from .types import (
    ZendeskComment,
    ZendeskGroup,
    ZendeskOrganization,
    ZendeskSearchResult,
    ZendeskTicket,
    ZendeskUser,
)

logger = logging.getLogger("toolsconnector.zendesk")


class Zendesk(BaseConnector):
    """Connect to Zendesk to manage tickets, users, and support workflows.

    Supports Basic auth with email/token and API token. Credentials
    format: ``email:api_token:subdomain``. The subdomain is used to
    construct the base URL: ``https://{subdomain}.zendesk.com/api/v2``.
    """

    name = "zendesk"
    display_name = "Zendesk"
    category = ConnectorCategory.CRM
    protocol = ProtocolType.REST
    base_url = "https://{subdomain}.zendesk.com/api/v2"
    description = (
        "Connect to Zendesk to manage support tickets, users, and search across your help desk."
    )
    _rate_limit_config = RateLimitSpec(rate=400, period=60, burst=50)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Initialise the httpx async client with Zendesk Basic auth.

        Parses credentials as ``email:api_token:subdomain`` and builds
        HTTP Basic auth header using ``email/token:api_token``.
        """
        creds = self._credentials or "::"
        parts = creds.split(":", 2)
        email = parts[0] if len(parts) > 0 else ""
        api_token = parts[1] if len(parts) > 1 else ""
        subdomain = parts[2] if len(parts) > 2 else ""

        auth_string = f"{email}/token:{api_token}"
        token = base64.b64encode(auth_string.encode()).decode()

        resolved_url = self._base_url or self.__class__.base_url.format(subdomain=subdomain)

        headers: dict[str, str] = {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        self._client = httpx.AsyncClient(
            base_url=resolved_url,
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
        """Send an authenticated request to the Zendesk API.

        Args:
            method: HTTP method (GET, POST, PUT, etc.).
            path: API path relative to base_url.
            params: Query parameters.
            json_body: JSON body for POST/PUT requests.

        Returns:
            httpx.Response object.

        Raises:
            httpx.HTTPStatusError: On 4xx/5xx responses.
        """
        resp = await self._client.request(
            method,
            path,
            params=params,
            json=json_body,
        )

        remaining = resp.headers.get("X-Rate-Limit-Remaining")
        if remaining is not None:
            logger.debug("Zendesk rate-limit remaining: %s", remaining)

        raise_typed_for_status(resp, connector=self.name)
        return resp

    def _build_cursor_page_state(self, body: dict[str, Any]) -> PageState:
        """Build a PageState from Zendesk cursor pagination response.

        Args:
            body: Parsed JSON response body.

        Returns:
            PageState with cursor set to after_cursor if more pages exist.
        """
        meta = body.get("meta") or {}
        has_more = meta.get("has_more", False)
        after_cursor = meta.get("after_cursor")
        return PageState(has_more=has_more, cursor=after_cursor)

    # ------------------------------------------------------------------
    # Actions -- Tickets
    # ------------------------------------------------------------------

    @action("List tickets from Zendesk")
    async def list_tickets(
        self,
        status: Optional[str] = None,
        limit: int = 25,
        page: Optional[int] = None,
    ) -> PaginatedList[ZendeskTicket]:
        """List tickets with optional status filter.

        Args:
            status: Filter by ticket status (new, open, pending, etc.).
            limit: Maximum number of tickets per page (1-100).
            page: Page number for offset pagination.

        Returns:
            Paginated list of ZendeskTicket objects.
        """
        params: dict[str, Any] = {"per_page": min(limit, 100)}
        if status is not None:
            params["status"] = status
        if page is not None:
            params["page"] = page

        resp = await self._request("GET", "/tickets.json", params=params)
        body = resp.json()

        items = [parse_ticket(t) for t in body.get("tickets", [])]

        # Zendesk tickets endpoint uses next_page URL pagination
        next_page = body.get("next_page")
        has_more = next_page is not None
        page_state = PageState(has_more=has_more, cursor=next_page)

        result = PaginatedList(
            items=items,
            page_state=page_state,
            total_count=body.get("count"),
        )
        result._fetch_next = (
            (
                lambda: self.list_tickets(
                    status=status,
                    limit=limit,
                    page=(page or 1) + 1,
                )
            )
            if has_more
            else None
        )
        return result

    @action("Get a single Zendesk ticket by ID")
    async def get_ticket(self, ticket_id: int) -> ZendeskTicket:
        """Retrieve a single ticket by its ID.

        Args:
            ticket_id: The Zendesk ticket ID.

        Returns:
            ZendeskTicket object.
        """
        resp = await self._request("GET", f"/tickets/{ticket_id}.json")
        return parse_ticket(resp.json()["ticket"])

    @action("Create a new Zendesk ticket", dangerous=True)
    async def create_ticket(
        self,
        subject: str,
        description: str,
        priority: Optional[str] = None,
        requester_email: Optional[str] = None,
    ) -> ZendeskTicket:
        """Create a new support ticket.

        Args:
            subject: Ticket subject line.
            description: Ticket body/description.
            priority: Priority level (urgent, high, normal, low).
            requester_email: Email of the requester.

        Returns:
            The created ZendeskTicket object.
        """
        comment_body: dict[str, Any] = {"body": description}
        ticket_data: dict[str, Any] = {
            "subject": subject,
            "comment": comment_body,
        }
        if priority is not None:
            ticket_data["priority"] = priority
        if requester_email is not None:
            ticket_data["requester"] = {"email": requester_email}

        resp = await self._request(
            "POST",
            "/tickets.json",
            json_body={"ticket": ticket_data},
        )
        return parse_ticket(resp.json()["ticket"])

    @action("Update an existing Zendesk ticket", dangerous=True)
    async def update_ticket(
        self,
        ticket_id: int,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> ZendeskTicket:
        """Update an existing ticket's status, priority, or add a comment.

        Args:
            ticket_id: The Zendesk ticket ID.
            status: New ticket status (open, pending, solved, closed).
            priority: New priority level.
            comment: Comment text to add to the ticket.

        Returns:
            The updated ZendeskTicket object.
        """
        ticket_data: dict[str, Any] = {}
        if status is not None:
            ticket_data["status"] = status
        if priority is not None:
            ticket_data["priority"] = priority
        if comment is not None:
            ticket_data["comment"] = {"body": comment, "public": True}

        resp = await self._request(
            "PUT",
            f"/tickets/{ticket_id}.json",
            json_body={"ticket": ticket_data},
        )
        return parse_ticket(resp.json()["ticket"])

    # ------------------------------------------------------------------
    # Actions -- Comments
    # ------------------------------------------------------------------

    @action("Add a comment to a Zendesk ticket", dangerous=True)
    async def add_comment(
        self,
        ticket_id: int,
        body: str,
        public: bool = True,
    ) -> ZendeskTicket:
        """Add a comment to an existing ticket.

        Args:
            ticket_id: The Zendesk ticket ID.
            body: Comment body text.
            public: Whether the comment is public (True) or internal (False).

        Returns:
            The updated ZendeskTicket object.
        """
        ticket_data: dict[str, Any] = {
            "comment": {"body": body, "public": public},
        }

        resp = await self._request(
            "PUT",
            f"/tickets/{ticket_id}.json",
            json_body={"ticket": ticket_data},
        )
        return parse_ticket(resp.json()["ticket"])

    # ------------------------------------------------------------------
    # Actions -- Users
    # ------------------------------------------------------------------

    @action("List users in Zendesk")
    async def list_users(
        self,
        limit: int = 25,
        page: Optional[int] = None,
    ) -> PaginatedList[ZendeskUser]:
        """List users with offset pagination.

        Args:
            limit: Maximum number of users per page (1-100).
            page: Page number for offset pagination.

        Returns:
            Paginated list of ZendeskUser objects.
        """
        params: dict[str, Any] = {"per_page": min(limit, 100)}
        if page is not None:
            params["page"] = page

        resp = await self._request("GET", "/users.json", params=params)
        body = resp.json()

        items = [parse_user(u) for u in body.get("users", [])]

        next_page = body.get("next_page")
        has_more = next_page is not None
        page_state = PageState(has_more=has_more, cursor=next_page)

        result = PaginatedList(
            items=items,
            page_state=page_state,
            total_count=body.get("count"),
        )
        result._fetch_next = (
            (
                lambda: self.list_users(
                    limit=limit,
                    page=(page or 1) + 1,
                )
            )
            if has_more
            else None
        )
        return result

    @action("Get a single Zendesk user by ID")
    async def get_user(self, user_id: int) -> ZendeskUser:
        """Retrieve a single user by their ID.

        Args:
            user_id: The Zendesk user ID.

        Returns:
            ZendeskUser object.
        """
        resp = await self._request("GET", f"/users/{user_id}.json")
        return parse_user(resp.json()["user"])

    # ------------------------------------------------------------------
    # Actions -- Search
    # ------------------------------------------------------------------

    @action("Search across Zendesk resources")
    async def search(
        self,
        query: str,
        limit: int = 25,
    ) -> PaginatedList[ZendeskSearchResult]:
        """Search across tickets, users, and organizations.

        Uses the Zendesk search API with its query syntax (e.g.
        ``type:ticket status:open``).

        Args:
            query: Zendesk search query string.
            limit: Maximum number of results per page.

        Returns:
            Paginated list of ZendeskSearchResult objects.
        """
        params: dict[str, Any] = {
            "query": query,
            "per_page": min(limit, 100),
        }

        resp = await self._request("GET", "/search.json", params=params)
        body = resp.json()

        items = [parse_search_result(r) for r in body.get("results", [])]

        next_page = body.get("next_page")
        has_more = next_page is not None
        page_state = PageState(has_more=has_more, cursor=next_page)

        result = PaginatedList(
            items=items,
            page_state=page_state,
            total_count=body.get("count"),
        )
        return result

    # ------------------------------------------------------------------
    # Actions -- Ticket management (extended)
    # ------------------------------------------------------------------

    @action("Delete a Zendesk ticket", dangerous=True)
    async def delete_ticket(self, ticket_id: int) -> bool:
        """Permanently delete a Zendesk ticket.

        Args:
            ticket_id: The Zendesk ticket ID.

        Returns:
            True if the ticket was deleted successfully.
        """
        resp = await self._request("DELETE", f"/tickets/{ticket_id}.json")
        return resp.status_code in (200, 204)

    @action("Assign a ticket to an agent")
    async def assign_ticket(
        self,
        ticket_id: int,
        assignee_id: int,
    ) -> ZendeskTicket:
        """Assign a ticket to a specific agent.

        Args:
            ticket_id: The Zendesk ticket ID.
            assignee_id: The user ID of the agent to assign.

        Returns:
            The updated ZendeskTicket.
        """
        resp = await self._request(
            "PUT",
            f"/tickets/{ticket_id}.json",
            json_body={"ticket": {"assignee_id": assignee_id}},
        )
        return parse_ticket(resp.json()["ticket"])

    # ------------------------------------------------------------------
    # Actions -- Groups
    # ------------------------------------------------------------------

    @action("List agent groups in Zendesk")
    async def list_groups(
        self,
        limit: Optional[int] = None,
    ) -> list[ZendeskGroup]:
        """List all agent groups.

        Args:
            limit: Maximum number of groups to return.

        Returns:
            List of ZendeskGroup objects.
        """
        params: dict[str, Any] = {}
        if limit is not None:
            params["per_page"] = min(limit, 100)
        resp = await self._request(
            "GET",
            "/groups.json",
            params=params or None,
        )
        body = resp.json()
        return [
            ZendeskGroup(
                id=g["id"],
                name=g.get("name"),
                description=g.get("description"),
                default=g.get("default", False),
                deleted=g.get("deleted", False),
                created_at=g.get("created_at"),
                updated_at=g.get("updated_at"),
            )
            for g in body.get("groups", [])
        ]

    # ------------------------------------------------------------------
    # Actions -- Tags
    # ------------------------------------------------------------------

    @action("List all tags used in Zendesk")
    async def list_tags(self) -> list[str]:
        """List all tags currently used across tickets.

        Returns:
            List of tag name strings.
        """
        resp = await self._request("GET", "/tags.json")
        body = resp.json()
        return [t.get("name", "") for t in body.get("tags", [])]

    # ------------------------------------------------------------------
    # Actions -- User management (extended)
    # ------------------------------------------------------------------

    @action("Create a new Zendesk user", dangerous=True)
    async def create_user(
        self,
        name: str,
        email: str,
    ) -> ZendeskUser:
        """Create a new user in Zendesk.

        Args:
            name: The user's full name.
            email: The user's email address.

        Returns:
            The created ZendeskUser object.
        """
        user_data: dict[str, Any] = {
            "name": name,
            "email": email,
        }
        resp = await self._request(
            "POST",
            "/users.json",
            json_body={"user": user_data},
        )
        return parse_user(resp.json()["user"])

    @action("Update an existing Zendesk user")
    async def update_user(
        self,
        user_id: int,
        name: Optional[str] = None,
        email: Optional[str] = None,
    ) -> ZendeskUser:
        """Update a user's name or email.

        Args:
            user_id: The Zendesk user ID.
            name: New name for the user.
            email: New email for the user.

        Returns:
            The updated ZendeskUser object.
        """
        user_data: dict[str, Any] = {}
        if name is not None:
            user_data["name"] = name
        if email is not None:
            user_data["email"] = email

        resp = await self._request(
            "PUT",
            f"/users/{user_id}.json",
            json_body={"user": user_data},
        )
        return parse_user(resp.json()["user"])

    # ------------------------------------------------------------------
    # Actions -- Ticket comments
    # ------------------------------------------------------------------

    @action("List comments on a Zendesk ticket")
    async def list_ticket_comments(
        self,
        ticket_id: int,
    ) -> list[ZendeskComment]:
        """List all comments (conversation) on a ticket.

        Args:
            ticket_id: The Zendesk ticket ID.

        Returns:
            List of ZendeskComment objects.
        """
        resp = await self._request(
            "GET",
            f"/tickets/{ticket_id}/comments.json",
        )
        body = resp.json()
        return [
            ZendeskComment(
                id=c["id"],
                type=c.get("type"),
                body=c.get("body"),
                html_body=c.get("html_body"),
                plain_body=c.get("plain_body"),
                public=c.get("public", True),
                author_id=c.get("author_id"),
                created_at=c.get("created_at"),
            )
            for c in body.get("comments", [])
        ]

    # ------------------------------------------------------------------
    # Actions -- Organizations
    # ------------------------------------------------------------------

    @action("List organizations in Zendesk")
    async def list_organizations(
        self,
        limit: int = 25,
        page: Optional[int] = None,
    ) -> PaginatedList[ZendeskOrganization]:
        """List organizations with offset pagination.

        Args:
            limit: Maximum number of organizations per page (1-100).
            page: Page number for offset pagination.

        Returns:
            Paginated list of ZendeskOrganization objects.
        """
        params: dict[str, Any] = {"per_page": min(limit, 100)}
        if page is not None:
            params["page"] = page

        resp = await self._request(
            "GET",
            "/organizations.json",
            params=params,
        )
        body = resp.json()

        items = [
            ZendeskOrganization(
                id=o["id"],
                name=o.get("name"),
                details=o.get("details"),
                notes=o.get("notes"),
                group_id=o.get("group_id"),
                domain_names=o.get("domain_names", []),
                tags=o.get("tags", []),
                shared_tickets=o.get("shared_tickets", False),
                shared_comments=o.get("shared_comments", False),
                external_id=o.get("external_id"),
                created_at=o.get("created_at"),
                updated_at=o.get("updated_at"),
            )
            for o in body.get("organizations", [])
        ]

        next_page = body.get("next_page")
        has_more = next_page is not None

        return PaginatedList(
            items=items,
            page_state=PageState(has_more=has_more, cursor=next_page),
            total_count=body.get("count"),
        )
