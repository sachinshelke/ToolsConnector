"""Google Calendar connector -- manage events and calendars via the Calendar API v3.

Uses httpx for direct HTTP calls against the Google Calendar REST API.
Expects an OAuth 2.0 access token passed as ``credentials``.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx

from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import ConnectorCategory, ProtocolType, RateLimitSpec
from toolsconnector.types import PageState, PaginatedList

from .types import (
    Calendar,
    CalendarACL,
    CalendarColors,
    CalendarEvent,
    EventAttendee,
    EventTime,
    FreeBusyCalendar,
)


def _parse_event_time(data: Optional[dict[str, Any]]) -> Optional[EventTime]:
    """Parse a Calendar API event time object.

    Args:
        data: Raw dict with dateTime/date/timeZone keys, or None.

    Returns:
        Parsed EventTime or None if input is None.
    """
    if data is None:
        return None
    return EventTime(
        date_time=data.get("dateTime"),
        date=data.get("date"),
        time_zone=data.get("timeZone"),
    )


def _parse_attendees(raw: list[dict[str, Any]]) -> list[EventAttendee]:
    """Parse a list of attendee dicts from the Calendar API.

    Args:
        raw: List of attendee resource dicts.

    Returns:
        List of parsed EventAttendee models.
    """
    attendees: list[EventAttendee] = []
    for a in raw:
        attendees.append(
            EventAttendee(
                email=a.get("email", ""),
                display_name=a.get("displayName"),
                response_status=a.get("responseStatus", "needsAction"),
                optional=a.get("optional", False),
                organizer=a.get("organizer", False),
                **{"self": a.get("self", False)},
            )
        )
    return attendees


def _parse_event(data: dict[str, Any]) -> CalendarEvent:
    """Parse a Calendar API event resource into a CalendarEvent model.

    Args:
        data: Raw JSON dict from the Calendar API.

    Returns:
        Populated CalendarEvent instance.
    """
    # Extract conference link from conferenceData if present
    conference_link: Optional[str] = None
    conf_data = data.get("conferenceData", {})
    entry_points = conf_data.get("entryPoints", [])
    for ep in entry_points:
        if ep.get("entryPointType") == "video":
            conference_link = ep.get("uri")
            break

    return CalendarEvent(
        id=data.get("id", ""),
        summary=data.get("summary", ""),
        description=data.get("description"),
        location=data.get("location"),
        start=_parse_event_time(data.get("start")),
        end=_parse_event_time(data.get("end")),
        status=data.get("status", "confirmed"),
        html_link=data.get("htmlLink"),
        created=data.get("created"),
        updated=data.get("updated"),
        creator_email=data.get("creator", {}).get("email"),
        organizer_email=data.get("organizer", {}).get("email"),
        attendees=_parse_attendees(data.get("attendees", [])),
        recurrence=data.get("recurrence", []),
        recurring_event_id=data.get("recurringEventId"),
        color_id=data.get("colorId"),
        hangout_link=data.get("hangoutLink"),
        conference_link=conference_link,
    )


def _build_event_time(date_time: Optional[str], time_zone: Optional[str]) -> dict[str, str]:
    """Build a Calendar API event time dict.

    Detects whether the input is a date-only (YYYY-MM-DD) or a full
    datetime and uses the appropriate key.

    Args:
        date_time: ISO 8601 date or datetime string.
        time_zone: IANA timezone string (e.g., 'America/New_York').

    Returns:
        Dict suitable for the Calendar API start/end fields.
    """
    result: dict[str, str] = {}
    if date_time:
        # Date-only format: YYYY-MM-DD (10 chars, no 'T')
        if len(date_time) == 10 and "T" not in date_time:
            result["date"] = date_time
        else:
            result["dateTime"] = date_time
    if time_zone:
        result["timeZone"] = time_zone
    return result


class GoogleCalendar(BaseConnector):
    """Connect to Google Calendar to manage events and calendars.

    Supports OAuth 2.0 authentication. Pass an access token as
    ``credentials`` when instantiating. Uses the Calendar REST API v3
    via direct httpx calls.
    """

    name = "gcalendar"
    display_name = "Google Calendar"
    category = ConnectorCategory.PRODUCTIVITY
    protocol = ProtocolType.REST
    base_url = "https://www.googleapis.com/calendar/v3"
    description = "Connect to Google Calendar to manage events and calendars."
    _rate_limit_config = RateLimitSpec(rate=600, period=60, burst=100)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_headers(self) -> dict[str, str]:
        """Build authorization headers for Calendar API requests.

        Returns:
            Dict with Authorization bearer header.
        """
        return {"Authorization": f"Bearer {self._credentials}"}

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """Execute an authenticated HTTP request against the Calendar API.

        Args:
            method: HTTP method (GET, POST, PUT, PATCH, DELETE).
            path: API path relative to base_url.
            **kwargs: Additional keyword arguments passed to httpx.

        Returns:
            Parsed JSON response as a dict.

        Raises:
            httpx.HTTPStatusError: If the API returns a non-2xx status.
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.request(
                method,
                f"{self._base_url}{path}",
                headers=self._get_headers(),
                **kwargs,
            )
            response.raise_for_status()
            if response.status_code == 204 or not response.content:
                return {}
            return response.json()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    @action("List calendar events", requires_scope="read")
    async def list_events(
        self,
        calendar_id: str = "primary",
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
        query: Optional[str] = None,
        max_results: int = 25,
        single_events: bool = True,
        order_by: str = "startTime",
        page_token: Optional[str] = None,
    ) -> PaginatedList[CalendarEvent]:
        """List events from a calendar.

        Args:
            calendar_id: Calendar ID ('primary' for the user's main calendar).
            time_min: Lower bound (inclusive) as RFC 3339 timestamp.
            time_max: Upper bound (exclusive) as RFC 3339 timestamp.
            query: Free-text search query across event fields.
            max_results: Maximum number of events per page (max 2500).
            single_events: If True, expand recurring events into instances.
            order_by: Sort order: 'startTime' (requires single_events=True) or 'updated'.
            page_token: Token for fetching the next page.

        Returns:
            Paginated list of CalendarEvent objects.
        """
        params: dict[str, Any] = {
            "maxResults": min(max_results, 2500),
            "singleEvents": str(single_events).lower(),
            "orderBy": order_by,
        }
        if time_min:
            params["timeMin"] = time_min
        if time_max:
            params["timeMax"] = time_max
        if query:
            params["q"] = query
        if page_token:
            params["pageToken"] = page_token

        data = await self._request(
            "GET",
            f"/calendars/{calendar_id}/events",
            params=params,
        )

        events = [_parse_event(e) for e in data.get("items", [])]
        next_token = data.get("nextPageToken")

        return PaginatedList(
            items=events,
            page_state=PageState(
                cursor=next_token,
                has_more=next_token is not None,
            ),
        )

    @action("Get a single event by ID", requires_scope="read")
    async def get_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
    ) -> CalendarEvent:
        """Retrieve a single calendar event by its ID.

        Args:
            event_id: The ID of the event to retrieve.
            calendar_id: Calendar ID ('primary' for the user's main calendar).

        Returns:
            The requested CalendarEvent object.
        """
        data = await self._request(
            "GET",
            f"/calendars/{calendar_id}/events/{event_id}",
        )
        event = _parse_event(data)
        return CalendarEvent(
            **{**event.model_dump(), "calendar_id": calendar_id},
        )

    @action("Create a calendar event", requires_scope="write", dangerous=True)
    async def create_event(
        self,
        summary: str,
        start: str,
        end: str,
        calendar_id: str = "primary",
        description: Optional[str] = None,
        location: Optional[str] = None,
        time_zone: Optional[str] = None,
        attendees: Optional[list[str]] = None,
        send_updates: str = "none",
    ) -> CalendarEvent:
        """Create a new calendar event.

        Args:
            summary: Event title/summary.
            start: Start time as ISO 8601 string (date or datetime).
            end: End time as ISO 8601 string (date or datetime).
            calendar_id: Calendar ID ('primary' for the user's main calendar).
            description: Optional event description (supports HTML).
            location: Optional event location.
            time_zone: IANA timezone (e.g., 'America/New_York'). Defaults
                to the calendar's timezone.
            attendees: Optional list of attendee email addresses.
            send_updates: Notification policy: 'all', 'externalOnly', or 'none'.

        Returns:
            The created CalendarEvent object.
        """
        event_body: dict[str, Any] = {
            "summary": summary,
            "start": _build_event_time(start, time_zone),
            "end": _build_event_time(end, time_zone),
        }
        if description:
            event_body["description"] = description
        if location:
            event_body["location"] = location
        if attendees:
            event_body["attendees"] = [{"email": e} for e in attendees]

        data = await self._request(
            "POST",
            f"/calendars/{calendar_id}/events",
            json=event_body,
            params={"sendUpdates": send_updates},
        )
        return _parse_event(data)

    @action("Update a calendar event", requires_scope="write", dangerous=True)
    async def update_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        summary: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        time_zone: Optional[str] = None,
        attendees: Optional[list[str]] = None,
        send_updates: str = "none",
    ) -> CalendarEvent:
        """Update an existing calendar event.

        Only provided fields will be updated. Uses PATCH semantics for
        partial updates.

        Args:
            event_id: The ID of the event to update.
            calendar_id: Calendar ID ('primary' for the user's main calendar).
            summary: New event title/summary.
            start: New start time as ISO 8601 string.
            end: New end time as ISO 8601 string.
            description: New event description.
            location: New event location.
            time_zone: IANA timezone for start/end.
            attendees: Replace attendees with this list of email addresses.
            send_updates: Notification policy: 'all', 'externalOnly', or 'none'.

        Returns:
            The updated CalendarEvent object.
        """
        event_body: dict[str, Any] = {}
        if summary is not None:
            event_body["summary"] = summary
        if description is not None:
            event_body["description"] = description
        if location is not None:
            event_body["location"] = location
        if start is not None:
            event_body["start"] = _build_event_time(start, time_zone)
        if end is not None:
            event_body["end"] = _build_event_time(end, time_zone)
        if attendees is not None:
            event_body["attendees"] = [{"email": e} for e in attendees]

        data = await self._request(
            "PATCH",
            f"/calendars/{calendar_id}/events/{event_id}",
            json=event_body,
            params={"sendUpdates": send_updates},
        )
        return _parse_event(data)

    @action("Delete a calendar event", requires_scope="write", dangerous=True)
    async def delete_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        send_updates: str = "none",
    ) -> None:
        """Delete a calendar event.

        Args:
            event_id: The ID of the event to delete.
            calendar_id: Calendar ID ('primary' for the user's main calendar).
            send_updates: Notification policy: 'all', 'externalOnly', or 'none'.

        Warning:
            This action permanently deletes the event. It cannot be undone.
        """
        await self._request(
            "DELETE",
            f"/calendars/{calendar_id}/events/{event_id}",
            params={"sendUpdates": send_updates},
        )

    @action("List calendars", requires_scope="read")
    async def list_calendars(
        self,
        page_token: Optional[str] = None,
        max_results: int = 100,
    ) -> PaginatedList[Calendar]:
        """List all calendars the user has access to.

        Args:
            page_token: Token for fetching the next page.
            max_results: Maximum number of calendars per page (max 250).

        Returns:
            Paginated list of Calendar objects.
        """
        params: dict[str, Any] = {
            "maxResults": min(max_results, 250),
        }
        if page_token:
            params["pageToken"] = page_token

        data = await self._request(
            "GET",
            "/users/me/calendarList",
            params=params,
        )

        calendars: list[Calendar] = []
        for cal in data.get("items", []):
            calendars.append(
                Calendar(
                    id=cal.get("id", ""),
                    summary=cal.get("summary", ""),
                    description=cal.get("description"),
                    time_zone=cal.get("timeZone"),
                    color_id=cal.get("colorId"),
                    background_color=cal.get("backgroundColor"),
                    foreground_color=cal.get("foregroundColor"),
                    selected=cal.get("selected", True),
                    primary=cal.get("primary", False),
                    access_role=cal.get("accessRole", "reader"),
                )
            )

        next_token = data.get("nextPageToken")
        return PaginatedList(
            items=calendars,
            page_state=PageState(
                cursor=next_token,
                has_more=next_token is not None,
            ),
        )

    # ------------------------------------------------------------------
    # Actions — Free/busy and advanced event operations
    # ------------------------------------------------------------------

    @action("Query free/busy information for calendars")
    async def get_free_busy(
        self,
        time_min: str,
        time_max: str,
        calendar_ids: list[str],
    ) -> list[FreeBusyCalendar]:
        """Query free/busy information for one or more calendars.

        Args:
            time_min: Start of the time range (ISO 8601 datetime).
            time_max: End of the time range (ISO 8601 datetime).
            calendar_ids: List of calendar IDs to query.

        Returns:
            List of FreeBusyCalendar objects with busy time ranges.
        """
        body: dict[str, Any] = {
            "timeMin": time_min,
            "timeMax": time_max,
            "items": [{"id": cid} for cid in calendar_ids],
        }
        data = await self._request(
            "POST",
            "/freeBusy",
            json=body,
        )
        calendars_data = data.get("calendars", {})
        results: list[FreeBusyCalendar] = []
        for cal_id, cal_info in calendars_data.items():
            results.append(
                FreeBusyCalendar(
                    calendar_id=cal_id,
                    busy=cal_info.get("busy", []),
                    errors=cal_info.get("errors", []),
                )
            )
        return results

    @action("List instances of a recurring event")
    async def list_event_instances(
        self,
        calendar_id: str,
        event_id: str,
    ) -> list[CalendarEvent]:
        """List all instances of a recurring event.

        Args:
            calendar_id: Calendar ID containing the event.
            event_id: The recurring event ID.

        Returns:
            List of CalendarEvent objects for each instance.
        """
        data = await self._request(
            "GET",
            f"/calendars/{calendar_id}/events/{event_id}/instances",
        )
        return [_parse_event(e) for e in data.get("items", [])]

    @action("Move an event to a different calendar")
    async def move_event(
        self,
        calendar_id: str,
        event_id: str,
        destination_calendar_id: str,
    ) -> CalendarEvent:
        """Move an event from one calendar to another.

        Args:
            calendar_id: Source calendar ID.
            event_id: The event ID to move.
            destination_calendar_id: Destination calendar ID.

        Returns:
            The moved CalendarEvent in its new calendar.
        """
        data = await self._request(
            "POST",
            f"/calendars/{calendar_id}/events/{event_id}/move",
            params={"destination": destination_calendar_id},
        )
        return _parse_event(data)

    # ------------------------------------------------------------------
    # Actions — Calendar management
    # ------------------------------------------------------------------

    @action("Create a new calendar", requires_scope="write", dangerous=True)
    async def create_calendar(
        self,
        summary: str,
        description: Optional[str] = None,
        time_zone: Optional[str] = None,
    ) -> Calendar:
        """Create a new secondary calendar.

        Args:
            summary: Title of the new calendar.
            description: Optional calendar description.
            time_zone: IANA timezone (e.g., 'America/New_York'). Defaults to
                the authenticated user's timezone.

        Returns:
            The created Calendar object.
        """
        body: dict[str, Any] = {"summary": summary}
        if description is not None:
            body["description"] = description
        if time_zone is not None:
            body["timeZone"] = time_zone

        data = await self._request("POST", "/calendars", json=body)
        return Calendar(
            id=data.get("id", ""),
            summary=data.get("summary", ""),
            description=data.get("description"),
            time_zone=data.get("timeZone"),
        )

    @action("Delete a calendar", requires_scope="write", dangerous=True)
    async def delete_calendar(self, calendar_id: str) -> None:
        """Permanently delete a secondary calendar.

        The primary calendar cannot be deleted.

        Args:
            calendar_id: The ID of the calendar to delete.

        Warning:
            This permanently deletes the calendar and all its events.
            It cannot be undone.
        """
        await self._request("DELETE", f"/calendars/{calendar_id}")

    @action("Update a calendar", requires_scope="write", dangerous=True)
    async def update_calendar(
        self,
        calendar_id: str,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        time_zone: Optional[str] = None,
    ) -> Calendar:
        """Update a calendar's metadata.

        Uses PUT semantics -- all provided fields replace existing values.
        Fields set to ``None`` are left unchanged.

        Args:
            calendar_id: The ID of the calendar to update.
            summary: New calendar title.
            description: New calendar description.
            time_zone: New IANA timezone.

        Returns:
            The updated Calendar object.
        """
        # GET current state to merge unchanged fields (PUT requires full body)
        current = await self._request("GET", f"/calendars/{calendar_id}")
        body: dict[str, Any] = {
            "summary": summary if summary is not None else current.get("summary", ""),
        }
        if description is not None:
            body["description"] = description
        elif "description" in current:
            body["description"] = current["description"]
        if time_zone is not None:
            body["timeZone"] = time_zone
        elif "timeZone" in current:
            body["timeZone"] = current["timeZone"]

        data = await self._request(
            "PUT",
            f"/calendars/{calendar_id}",
            json=body,
        )
        return Calendar(
            id=data.get("id", ""),
            summary=data.get("summary", ""),
            description=data.get("description"),
            time_zone=data.get("timeZone"),
        )

    @action("Clear all events from a calendar", requires_scope="write", dangerous=True)
    async def clear_calendar(self, calendar_id: str) -> None:
        """Remove all events from a calendar.

        Only works on primary calendars. The calendar itself is not deleted.

        Args:
            calendar_id: The ID of the calendar to clear.

        Warning:
            This permanently deletes every event in the calendar.
            It cannot be undone.
        """
        await self._request("POST", f"/calendars/{calendar_id}/clear")

    # ------------------------------------------------------------------
    # Actions — Calendar subscriptions (calendarList)
    # ------------------------------------------------------------------

    @action("Subscribe to an external calendar", requires_scope="write", dangerous=True)
    async def subscribe_calendar(self, calendar_id: str) -> Calendar:
        """Add an existing calendar to the authenticated user's calendar list.

        Use this to subscribe to a public or shared calendar by its ID
        (usually an email address).

        Args:
            calendar_id: The ID of the calendar to subscribe to.

        Returns:
            The subscribed Calendar entry.
        """
        data = await self._request(
            "POST",
            "/users/me/calendarList",
            json={"id": calendar_id},
        )
        return Calendar(
            id=data.get("id", ""),
            summary=data.get("summary", ""),
            description=data.get("description"),
            time_zone=data.get("timeZone"),
            color_id=data.get("colorId"),
            background_color=data.get("backgroundColor"),
            foreground_color=data.get("foregroundColor"),
            selected=data.get("selected", True),
            primary=data.get("primary", False),
            access_role=data.get("accessRole", "reader"),
        )

    @action("Unsubscribe from a calendar", requires_scope="write", dangerous=True)
    async def unsubscribe_calendar(self, calendar_id: str) -> None:
        """Remove a calendar from the authenticated user's calendar list.

        This only removes the subscription -- it does not delete the
        underlying calendar.

        Args:
            calendar_id: The ID of the calendar to unsubscribe from.
        """
        await self._request(
            "DELETE",
            f"/users/me/calendarList/{calendar_id}",
        )

    # ------------------------------------------------------------------
    # Actions — ACL (sharing)
    # ------------------------------------------------------------------

    @action("List access-control rules for a calendar", requires_scope="read")
    async def list_calendar_acl(
        self,
        calendar_id: str,
    ) -> list[CalendarACL]:
        """List all access-control rules on a calendar.

        Args:
            calendar_id: The ID of the calendar.

        Returns:
            List of CalendarACL rule entries.
        """
        data = await self._request(
            "GET",
            f"/calendars/{calendar_id}/acl",
        )
        rules: list[CalendarACL] = []
        for item in data.get("items", []):
            scope = item.get("scope", {})
            rules.append(
                CalendarACL(
                    id=item.get("id", ""),
                    role=item.get("role", ""),
                    scope_type=scope.get("type", ""),
                    scope_value=scope.get("value"),
                    etag=item.get("etag"),
                )
            )
        return rules

    @action("Add an access-control rule to a calendar", requires_scope="write", dangerous=True)
    async def add_calendar_acl(
        self,
        calendar_id: str,
        email: str,
        role: str = "reader",
    ) -> CalendarACL:
        """Grant a user access to a calendar.

        Args:
            calendar_id: The ID of the calendar to share.
            email: The email address of the user to grant access to.
            role: The access level: 'none', 'freeBusyReader', 'reader',
                'writer', or 'owner'.

        Returns:
            The created CalendarACL rule.
        """
        body: dict[str, Any] = {
            "role": role,
            "scope": {
                "type": "user",
                "value": email,
            },
        }
        data = await self._request(
            "POST",
            f"/calendars/{calendar_id}/acl",
            json=body,
        )
        scope = data.get("scope", {})
        return CalendarACL(
            id=data.get("id", ""),
            role=data.get("role", ""),
            scope_type=scope.get("type", ""),
            scope_value=scope.get("value"),
            etag=data.get("etag"),
        )

    @action("Remove an access-control rule from a calendar", requires_scope="write", dangerous=True)
    async def remove_calendar_acl(
        self,
        calendar_id: str,
        rule_id: str,
    ) -> None:
        """Remove an access-control rule from a calendar.

        Args:
            calendar_id: The ID of the calendar.
            rule_id: The ID of the ACL rule to delete.

        Warning:
            This revokes the user's access to the calendar immediately.
        """
        await self._request(
            "DELETE",
            f"/calendars/{calendar_id}/acl/{rule_id}",
        )

    # ------------------------------------------------------------------
    # Actions — Quick add and colors
    # ------------------------------------------------------------------

    @action("Quick-add an event using natural language", requires_scope="write", dangerous=True)
    async def quick_add_event(
        self,
        text: str,
        calendar_id: str = "primary",
    ) -> CalendarEvent:
        """Create an event from a natural language description.

        Google Calendar parses the text to extract summary, date, time,
        and other details (e.g., "Lunch with John tomorrow at noon").

        Args:
            text: Natural language description of the event.
            calendar_id: Calendar ID ('primary' for the user's main calendar).

        Returns:
            The created CalendarEvent parsed from the text.
        """
        data = await self._request(
            "POST",
            f"/calendars/{calendar_id}/events/quickAdd",
            params={"text": text},
        )
        return _parse_event(data)

    @action("Get available calendar and event colors", requires_scope="read")
    async def get_colors(self) -> CalendarColors:
        """Retrieve the set of colors available for calendars and events.

        Returns:
            CalendarColors with calendar and event color maps keyed by
            color ID, each containing ``background`` and ``foreground``
            hex strings.
        """
        data = await self._request("GET", "/colors")
        return CalendarColors(
            calendar=data.get("calendar", {}),
            event=data.get("event", {}),
            updated=data.get("updated"),
        )
