"""Calendly connector -- event types, scheduled events, and invitees via Calendly API v2."""

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

from .types import (
    CalendlyEvent,
    CalendlyEventType,
    CalendlyInvitee,
    CalendlyOrganizationMembership,
    CalendlyUser,
    CalendlyWebhook,
)


class Calendly(BaseConnector):
    """Connect to Calendly to manage scheduling, events, and invitees.

    Requires a personal access token or OAuth token passed as
    ``credentials``.  Uses cursor-based pagination via ``page_token``.
    """

    name = "calendly"
    display_name = "Calendly"
    category = ConnectorCategory.PRODUCTIVITY
    protocol = ProtocolType.REST
    base_url = "https://api.calendly.com"
    description = (
        "Connect to Calendly to manage event types, scheduled events, "
        "invitees, and webhook subscriptions."
    )
    _rate_limit_config = RateLimitSpec(rate=100, period=60, burst=20)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Initialise the async HTTP client with Bearer auth."""
        self._client = httpx.AsyncClient(
            base_url=self._base_url or self.__class__.base_url,
            headers={
                "Authorization": f"Bearer {self._credentials}",
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
        json: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Execute an HTTP request against the Calendly API.

        Args:
            method: HTTP method.
            path: API path relative to ``base_url``.
            json: JSON request body.
            params: Query parameters.

        Returns:
            Parsed JSON response dict.

        Raises:
            httpx.HTTPStatusError: On non-2xx responses.
        """
        response = await self._client.request(method, path, json=json, params=params)
        raise_typed_for_status(response, connector=self.name)
        if response.status_code == 204:
            return {}
        return response.json()

    @staticmethod
    def _extract_uuid(uri: str) -> str:
        """Extract the UUID from a Calendly URI.

        Args:
            uri: A full Calendly resource URI.

        Returns:
            The UUID portion of the URI.
        """
        return uri.rsplit("/", 1)[-1] if "/" in uri else uri

    @staticmethod
    def _parse_user(data: dict[str, Any]) -> CalendlyUser:
        """Parse raw JSON into a CalendlyUser."""
        return CalendlyUser(
            uri=data.get("uri", ""),
            name=data.get("name", ""),
            email=data.get("email"),
            slug=data.get("slug"),
            scheduling_url=data.get("scheduling_url"),
            timezone=data.get("timezone"),
            avatar_url=data.get("avatar_url"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            current_organization=data.get("current_organization"),
        )

    @staticmethod
    def _parse_event_type(data: dict[str, Any]) -> CalendlyEventType:
        """Parse raw JSON into a CalendlyEventType."""
        return CalendlyEventType(
            uri=data.get("uri", ""),
            name=data.get("name", ""),
            slug=data.get("slug"),
            active=data.get("active", True),
            kind=data.get("kind"),
            scheduling_url=data.get("scheduling_url"),
            duration=data.get("duration"),
            type=data.get("type"),
            color=data.get("color"),
            description_plain=data.get("description_plain"),
            description_html=data.get("description_html"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )

    @staticmethod
    def _parse_event(data: dict[str, Any]) -> CalendlyEvent:
        """Parse raw JSON into a CalendlyEvent."""
        return CalendlyEvent(
            uri=data.get("uri", ""),
            name=data.get("name", ""),
            status=data.get("status", "active"),
            start_time=data.get("start_time"),
            end_time=data.get("end_time"),
            event_type=data.get("event_type"),
            location=data.get("location"),
            invitees_counter=data.get("invitees_counter"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            event_memberships=data.get("event_memberships", []),
            cancellation=data.get("cancellation"),
        )

    @staticmethod
    def _parse_invitee(data: dict[str, Any]) -> CalendlyInvitee:
        """Parse raw JSON into a CalendlyInvitee."""
        return CalendlyInvitee(
            uri=data.get("uri", ""),
            name=data.get("name", ""),
            email=data.get("email"),
            status=data.get("status", "active"),
            timezone=data.get("timezone"),
            event=data.get("event"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            canceled=data.get("canceled", False),
            cancellation=data.get("cancellation"),
            questions_and_answers=data.get("questions_and_answers", []),
        )

    @staticmethod
    def _parse_webhook(data: dict[str, Any]) -> CalendlyWebhook:
        """Parse raw JSON into a CalendlyWebhook."""
        return CalendlyWebhook(
            uri=data.get("uri", ""),
            callback_url=data.get("callback_url", ""),
            state=data.get("state", "active"),
            events=data.get("events", []),
            scope=data.get("scope", "user"),
            organization=data.get("organization"),
            user=data.get("user"),
            creator=data.get("creator"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )

    @staticmethod
    def _extract_page_token(pagination: dict[str, Any]) -> Optional[str]:
        """Extract the next page token from Calendly pagination info.

        Args:
            pagination: The ``pagination`` object from the API response.

        Returns:
            The next page token, or None if no more pages.
        """
        return pagination.get("next_page_token")

    # ------------------------------------------------------------------
    # Actions -- User
    # ------------------------------------------------------------------

    @action("Get the current authenticated user")
    async def get_current_user(self) -> CalendlyUser:
        """Retrieve the currently authenticated Calendly user.

        Returns:
            The authenticated CalendlyUser.
        """
        data = await self._request("GET", "/users/me")
        resource = data.get("resource", data)
        return self._parse_user(resource)

    # ------------------------------------------------------------------
    # Actions -- Event Types
    # ------------------------------------------------------------------

    @action("List event types for a user")
    async def list_event_types(
        self,
        user_uri: str,
        limit: int = 20,
        page_token: Optional[str] = None,
    ) -> PaginatedList[CalendlyEventType]:
        """List available event types (meeting templates) for a user.

        Args:
            user_uri: The Calendly user URI to list event types for.
            limit: Maximum results per page (max 100).
            page_token: Cursor from a previous response for the next page.

        Returns:
            Paginated list of CalendlyEventType objects.
        """
        params: dict[str, Any] = {
            "user": user_uri,
            "count": min(limit, 100),
        }
        if page_token:
            params["page_token"] = page_token

        data = await self._request("GET", "/event_types", params=params)

        collection = data.get("collection", [])
        event_types = [self._parse_event_type(et) for et in collection]
        pagination = data.get("pagination", {})
        next_token = self._extract_page_token(pagination)

        return PaginatedList(
            items=event_types,
            page_state=PageState(
                cursor=next_token,
                has_more=next_token is not None,
            ),
        )

    # ------------------------------------------------------------------
    # Actions -- Scheduled Events
    # ------------------------------------------------------------------

    @action("List scheduled events for a user")
    async def list_scheduled_events(
        self,
        user_uri: str,
        status: Optional[str] = None,
        min_start_time: Optional[str] = None,
        max_start_time: Optional[str] = None,
        limit: int = 20,
        page_token: Optional[str] = None,
    ) -> PaginatedList[CalendlyEvent]:
        """List scheduled events (meetings) for a user.

        Args:
            user_uri: The Calendly user URI.
            status: Filter by status (``"active"`` or ``"canceled"``).
            min_start_time: ISO 8601 lower bound on event start time.
            max_start_time: ISO 8601 upper bound on event start time.
            limit: Maximum results per page (max 100).
            page_token: Cursor from a previous response for the next page.

        Returns:
            Paginated list of CalendlyEvent objects.
        """
        params: dict[str, Any] = {
            "user": user_uri,
            "count": min(limit, 100),
        }
        if status:
            params["status"] = status
        if min_start_time:
            params["min_start_time"] = min_start_time
        if max_start_time:
            params["max_start_time"] = max_start_time
        if page_token:
            params["page_token"] = page_token

        data = await self._request("GET", "/scheduled_events", params=params)

        collection = data.get("collection", [])
        events = [self._parse_event(e) for e in collection]
        pagination = data.get("pagination", {})
        next_token = self._extract_page_token(pagination)

        return PaginatedList(
            items=events,
            page_state=PageState(
                cursor=next_token,
                has_more=next_token is not None,
            ),
        )

    @action("Get a single scheduled event")
    async def get_event(self, event_uuid: str) -> CalendlyEvent:
        """Retrieve a single scheduled event by its UUID.

        Args:
            event_uuid: The UUID of the scheduled event.

        Returns:
            The requested CalendlyEvent.
        """
        data = await self._request("GET", f"/scheduled_events/{event_uuid}")
        resource = data.get("resource", data)
        return self._parse_event(resource)

    @action("Cancel a scheduled event", dangerous=True)
    async def cancel_event(
        self,
        event_uuid: str,
        reason: Optional[str] = None,
    ) -> CalendlyEvent:
        """Cancel a scheduled event.

        Args:
            event_uuid: The UUID of the scheduled event.
            reason: Optional cancellation reason.

        Returns:
            The canceled CalendlyEvent.
        """
        body: dict[str, Any] = {}
        if reason:
            body["reason"] = reason

        # Issue the cancellation. The response payload is intentionally
        # discarded — we re-fetch the event below to return the full
        # post-cancellation state to the caller.
        await self._request(
            "POST",
            f"/scheduled_events/{event_uuid}/cancellation",
            json=body,
        )
        return await self.get_event(event_uuid)

    # ------------------------------------------------------------------
    # Actions -- Invitees
    # ------------------------------------------------------------------

    @action("List invitees for a scheduled event")
    async def list_invitees(
        self,
        event_uuid: str,
        limit: int = 20,
        page_token: Optional[str] = None,
    ) -> PaginatedList[CalendlyInvitee]:
        """List invitees of a scheduled event.

        Args:
            event_uuid: The UUID of the scheduled event.
            limit: Maximum results per page (max 100).
            page_token: Cursor from a previous response for the next page.

        Returns:
            Paginated list of CalendlyInvitee objects.
        """
        params: dict[str, Any] = {
            "count": min(limit, 100),
        }
        if page_token:
            params["page_token"] = page_token

        data = await self._request(
            "GET",
            f"/scheduled_events/{event_uuid}/invitees",
            params=params,
        )

        collection = data.get("collection", [])
        invitees = [self._parse_invitee(inv) for inv in collection]
        pagination = data.get("pagination", {})
        next_token = self._extract_page_token(pagination)

        return PaginatedList(
            items=invitees,
            page_state=PageState(
                cursor=next_token,
                has_more=next_token is not None,
            ),
        )

    # ------------------------------------------------------------------
    # Actions -- Webhooks
    # ------------------------------------------------------------------

    @action("List webhook subscriptions")
    async def list_webhooks(
        self,
        organization_uri: str,
        scope: str = "organization",
    ) -> PaginatedList[CalendlyWebhook]:
        """List webhook subscriptions for an organization.

        Args:
            organization_uri: The Calendly organization URI.
            scope: Webhook scope (``"organization"`` or ``"user"``).

        Returns:
            Paginated list of CalendlyWebhook objects.
        """
        params: dict[str, Any] = {
            "organization": organization_uri,
            "scope": scope,
        }
        data = await self._request("GET", "/webhook_subscriptions", params=params)

        collection = data.get("collection", [])
        webhooks = [self._parse_webhook(w) for w in collection]
        pagination = data.get("pagination", {})
        next_token = self._extract_page_token(pagination)

        return PaginatedList(
            items=webhooks,
            page_state=PageState(
                cursor=next_token,
                has_more=next_token is not None,
            ),
        )

    @action("Create a webhook subscription", dangerous=True)
    async def create_webhook(
        self,
        url: str,
        events: list[str],
        organization_uri: str,
        scope: str = "organization",
    ) -> CalendlyWebhook:
        """Create a new webhook subscription.

        Args:
            url: The callback URL for webhook delivery.
            events: List of event types to subscribe to
                (e.g. ``["invitee.created", "invitee.canceled"]``).
            organization_uri: The Calendly organization URI.
            scope: Webhook scope (``"organization"`` or ``"user"``).

        Returns:
            The created CalendlyWebhook.
        """
        body: dict[str, Any] = {
            "url": url,
            "events": events,
            "organization": organization_uri,
            "scope": scope,
        }
        data = await self._request("POST", "/webhook_subscriptions", json=body)
        resource = data.get("resource", data)
        return self._parse_webhook(resource)

    # ------------------------------------------------------------------
    # Actions -- Organization and routing
    # ------------------------------------------------------------------

    @action("Get organization details")
    async def get_organization(self) -> dict[str, Any]:
        """Get the authenticated user's organization details.

        Returns:
            Dict with organization resource data.
        """
        # First get the current user to find org URI
        user_data = await self._request("GET", "/users/me")
        resource = user_data.get("resource", {})
        org_uri = resource.get("current_organization")
        if not org_uri:
            return resource

        # Extract org UUID from URI
        org_uuid = org_uri.rstrip("/").split("/")[-1]
        org_data = await self._request(
            "GET",
            f"/organizations/{org_uuid}",
        )
        return org_data.get("resource", org_data)

    @action("List routing forms")
    async def list_routing_forms(self) -> list[dict[str, Any]]:
        """List all routing forms in the organization.

        Returns:
            List of routing form resource dicts.
        """
        # Get current user's org
        user_data = await self._request("GET", "/users/me")
        resource = user_data.get("resource", {})
        org_uri = resource.get("current_organization", "")

        data = await self._request(
            "GET",
            "/routing_forms",
            params={"organization": org_uri},
        )
        return data.get("collection", [])

    # ------------------------------------------------------------------
    # Actions -- Event type details
    # ------------------------------------------------------------------

    @action("Get a single event type by UUID")
    async def get_event_type(
        self,
        event_type_uuid: str,
    ) -> CalendlyEventType:
        """Retrieve a single event type by its UUID.

        Args:
            event_type_uuid: The UUID of the event type.

        Returns:
            The requested CalendlyEventType.
        """
        data = await self._request(
            "GET",
            f"/event_types/{event_type_uuid}",
        )
        resource = data.get("resource", data)
        return self._parse_event_type(resource)

    # ------------------------------------------------------------------
    # Actions -- Availability
    # ------------------------------------------------------------------

    @action("List available times for an event type")
    async def list_available_times(
        self,
        event_type_uuid: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """List available time slots for scheduling an event type.

        Args:
            event_type_uuid: The UUID of the event type.
            start: ISO 8601 start of availability window.
            end: ISO 8601 end of availability window.

        Returns:
            List of available time slot dicts with start_time and
            invitees_remaining.
        """
        params: dict[str, Any] = {
            "event_type": f"https://api.calendly.com/event_types/{event_type_uuid}",
        }
        if start:
            params["start_time"] = start
        if end:
            params["end_time"] = end

        data = await self._request(
            "GET",
            "/event_type_available_times",
            params=params,
        )
        return data.get("collection", [])

    # ------------------------------------------------------------------
    # Actions -- Invitee details
    # ------------------------------------------------------------------

    @action("Get a single invitee for a scheduled event")
    async def get_invitee(
        self,
        event_uuid: str,
        invitee_uuid: str,
    ) -> CalendlyInvitee:
        """Retrieve a single invitee of a scheduled event.

        Args:
            event_uuid: The UUID of the scheduled event.
            invitee_uuid: The UUID of the invitee.

        Returns:
            The requested CalendlyInvitee.
        """
        data = await self._request(
            "GET",
            f"/scheduled_events/{event_uuid}/invitees/{invitee_uuid}",
        )
        resource = data.get("resource", data)
        return self._parse_invitee(resource)

    # ------------------------------------------------------------------
    # Actions -- Invitee cancellation
    # ------------------------------------------------------------------

    @action("Cancel a scheduled event invitee", dangerous=True)
    async def cancel_invitee(
        self,
        event_uuid: str,
        reason: Optional[str] = None,
    ) -> None:
        """Cancel a scheduled event (effectively canceling the invitee).

        The Calendly v2 API cancels events, not individual invitees.
        This posts a cancellation to the scheduled event.

        Args:
            event_uuid: The UUID of the scheduled event.
            reason: Optional cancellation reason.
        """
        body: dict[str, Any] = {}
        if reason is not None:
            body["reason"] = reason

        await self._request(
            "POST",
            f"/scheduled_events/{event_uuid}/cancellation",
            json=body,
        )

    # ------------------------------------------------------------------
    # Actions -- Organization members
    # ------------------------------------------------------------------

    @action("List organization members")
    async def list_organization_members(
        self,
        organization_uri: str,
        limit: int = 20,
        page_token: Optional[str] = None,
    ) -> PaginatedList[CalendlyOrganizationMembership]:
        """List all members in a Calendly organization.

        Args:
            organization_uri: The Calendly organization URI.
            limit: Maximum results per page (max 100).
            page_token: Cursor from a previous response for the
                next page.

        Returns:
            Paginated list of CalendlyOrganizationMembership objects.
        """
        params: dict[str, Any] = {
            "organization": organization_uri,
            "count": min(limit, 100),
        }
        if page_token:
            params["page_token"] = page_token

        data = await self._request(
            "GET",
            "/organization_memberships",
            params=params,
        )

        collection = data.get("collection", [])
        members = [
            CalendlyOrganizationMembership(
                uri=m.get("uri", ""),
                role=m.get("role"),
                user=m.get("user"),
                organization=m.get("organization"),
                created_at=m.get("created_at"),
                updated_at=m.get("updated_at"),
            )
            for m in collection
        ]
        pagination = data.get("pagination", {})
        next_token = self._extract_page_token(pagination)

        return PaginatedList(
            items=members,
            page_state=PageState(
                cursor=next_token,
                has_more=next_token is not None,
            ),
        )

    @action("Delete a webhook subscription", dangerous=True)
    async def delete_webhook(
        self,
        webhook_id: str,
    ) -> bool:
        """Delete a webhook subscription.

        Args:
            webhook_id: The webhook UUID.

        Returns:
            True if the webhook was deleted.
        """
        await self._request(
            "DELETE",
            f"/webhook_subscriptions/{webhook_id}",
        )
        return True

    # ------------------------------------------------------------------
    # Actions — Availability & Scheduling
    # ------------------------------------------------------------------

    @action("List user availability schedules")
    async def list_availability_schedules(
        self,
        user_uri: str,
    ) -> list[dict[str, Any]]:
        """List availability schedules for a user.

        Args:
            user_uri: The user's URI (e.g., from get_current_user).

        Returns:
            List of availability schedule dicts.
        """
        data = await self._request(
            "GET",
            "/user_availability_schedules",
            params={"user": user_uri},
        )
        return data.get("collection", [])

    @action("Get user busy times")
    async def get_user_busy_times(
        self,
        user_uri: str,
        start_time: str,
        end_time: str,
    ) -> list[dict[str, Any]]:
        """Get busy time slots for a user within a date range.

        Useful for finding when a user is unavailable for scheduling.

        Args:
            user_uri: The user's URI.
            start_time: Start of range (ISO 8601 format).
            end_time: End of range (ISO 8601 format).

        Returns:
            List of busy time dicts with start_time and end_time.
        """
        data = await self._request(
            "GET",
            "/user_busy_times",
            params={
                "user": user_uri,
                "start_time": start_time,
                "end_time": end_time,
            },
        )
        return data.get("collection", [])

    @action("Schedule a meeting (create invitee)", dangerous=True)
    async def create_invitee(
        self,
        event_uuid: str,
        email: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        timezone: Optional[str] = None,
    ) -> dict[str, Any]:
        """Schedule a meeting by creating an invitee for an event.

        This is the Scheduling API endpoint that programmatically
        books a meeting slot.

        Args:
            event_uuid: The event UUID to schedule for.
            email: Invitee's email address.
            first_name: Invitee's first name.
            last_name: Invitee's last name.
            timezone: Invitee's timezone (IANA format).

        Returns:
            Created invitee dict with URI and scheduling details.
        """
        payload: dict[str, Any] = {"email": email}
        if first_name:
            payload["first_name"] = first_name
        if last_name:
            payload["last_name"] = last_name
        if timezone:
            payload["timezone"] = timezone
        data = await self._request(
            "POST",
            f"/scheduled_events/{event_uuid}/invitees",
            json=payload,
        )
        return data.get("resource", data)

    @action("List activity log events")
    async def list_activity_log(
        self,
        organization_uri: str,
        limit: int = 20,
        cursor: Optional[str] = None,
    ) -> PaginatedList[dict[str, Any]]:
        """List activity log events for the organization.

        Provides an audit trail of actions taken in the organization.

        Args:
            organization_uri: The organization URI.
            limit: Maximum entries to return.
            cursor: Pagination cursor.

        Returns:
            Paginated list of activity log dicts.
        """
        params: dict[str, Any] = {
            "organization": organization_uri,
            "count": limit,
        }
        if cursor:
            params["page_token"] = cursor
        data = await self._request(
            "GET",
            "/activity_log_entries",
            params=params,
        )
        entries = data.get("collection", [])
        pagination = data.get("pagination", {})
        next_token = pagination.get("next_page_token")
        return PaginatedList(
            items=entries,
            page_state=PageState(
                cursor=next_token,
                has_more=next_token is not None,
            ),
        )
