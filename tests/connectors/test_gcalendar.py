"""End-to-end tests for the Google Calendar connector using respx.

Pinned to Calendar API v3 at ``www.googleapis.com/calendar/v3``.
Auth is OAuth 2.0 bearer (`Authorization: Bearer ya29.…`).

Structure (5 rounds):
  Round 1 — happy path for all 20 actions
  Round 2 — defensive parsing + URL-path guards (calendar_id quoting, timezone variations)
  Round 3 — error matrix (401/403/404/410/429/500)
  Round 4 — transport errors + 204 No Content + recurring-event edge cases
  Round 5 — MCP + OpenAI schema + dangerous flag + sync wrappers + concurrency
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
import pytest_asyncio
import respx

from toolsconnector.connectors.gcalendar import GoogleCalendar
from toolsconnector.errors import ConnectionError as TCConnectionError
from toolsconnector.errors import (
    InvalidCredentialsError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
)
from toolsconnector.errors import TimeoutError as TCTimeoutError
from toolsconnector.errors import TransportError as TCTransportError


@pytest_asyncio.fixture
async def gc() -> GoogleCalendar:
    yield GoogleCalendar(credentials="ya29.fake_test_token")


# Canonical Calendar API response shapes.
_EVENT = {
    "id": "evt-abc-123",
    "summary": "Test Event",
    "description": "Event description",
    "location": "Conference Room A",
    "start": {"dateTime": "2026-06-01T10:00:00-07:00", "timeZone": "America/Los_Angeles"},
    "end": {"dateTime": "2026-06-01T11:00:00-07:00", "timeZone": "America/Los_Angeles"},
    "status": "confirmed",
    "htmlLink": "https://calendar.google.com/event?eid=abc",
    "created": "2026-05-28T12:00:00Z",
    "updated": "2026-05-28T12:00:00Z",
    "creator": {"email": "creator@example.com"},
    "organizer": {"email": "organizer@example.com"},
    "attendees": [
        {
            "email": "a@example.com",
            "displayName": "Alice",
            "responseStatus": "accepted",
            "self": False,
        },
    ],
}
_CAL = {
    "id": "cal-abc",
    "summary": "Test Calendar",
    "description": "calendar description",
    "timeZone": "America/Los_Angeles",
    "etag": "etag-1",
}
_ACL = {
    "id": "user:a@example.com",
    "role": "reader",
    "scope": {"type": "user", "value": "a@example.com"},
}


# ===========================================================================
# Round 1 — happy path for every action
# ===========================================================================


@pytest.mark.asyncio
async def test_list_events_with_filters(gc: GoogleCalendar) -> None:
    """list_events: GET /calendars/{id}/events with timeMin/timeMax/q/maxResults/etc."""
    with respx.mock(base_url="https://www.googleapis.com/calendar/v3") as mock:
        route = mock.get("/calendars/primary/events").mock(
            return_value=httpx.Response(200, json={"items": [_EVENT], "nextPageToken": "tok-2"})
        )
        page = await gc.alist_events(
            calendar_id="primary",
            time_min="2026-06-01T00:00:00Z",
            time_max="2026-06-30T23:59:59Z",
            query="standup",
            max_results=50,
            single_events=True,
            order_by="startTime",
        )
        assert len(page.items) == 1
        assert page.items[0].id == "evt-abc-123"
        assert page.page_state.cursor == "tok-2"
        assert page.page_state.has_more is True
        params = dict(route.calls.last.request.url.params)
        assert params["timeMin"] == "2026-06-01T00:00:00Z"
        assert params["q"] == "standup"
        assert params["singleEvents"] == "true"
        assert params["orderBy"] == "startTime"


@pytest.mark.asyncio
async def test_get_event_returns_typed_model(gc: GoogleCalendar) -> None:
    """get_event: GET /calendars/{id}/events/{eventId} → CalendarEvent."""
    with respx.mock(base_url="https://www.googleapis.com/calendar/v3") as mock:
        mock.get("/calendars/primary/events/evt-abc-123").mock(
            return_value=httpx.Response(200, json=_EVENT)
        )
        evt = await gc.aget_event(event_id="evt-abc-123", calendar_id="primary")
        assert evt.id == "evt-abc-123"
        assert evt.summary == "Test Event"
        assert evt.location == "Conference Room A"
        assert evt.start.date_time == "2026-06-01T10:00:00-07:00"
        assert len(evt.attendees) == 1
        assert evt.attendees[0].email == "a@example.com"


@pytest.mark.asyncio
async def test_create_event_with_datetime(gc: GoogleCalendar) -> None:
    """create_event: POST /calendars/{id}/events with start/end/attendees + sendUpdates."""
    with respx.mock(base_url="https://www.googleapis.com/calendar/v3") as mock:
        route = mock.post("/calendars/primary/events").mock(
            return_value=httpx.Response(200, json=_EVENT)
        )
        evt = await gc.acreate_event(
            summary="Lunch",
            start="2026-06-01T12:00:00-07:00",
            end="2026-06-01T13:00:00-07:00",
            calendar_id="primary",
            description="weekly sync",
            location="Room A",
            time_zone="America/Los_Angeles",
            attendees=["a@example.com", "b@example.com"],
            send_updates="all",
        )
        assert evt.id == "evt-abc-123"
        body = route.calls.last.request.read()
        assert b'"summary":"Lunch"' in body
        assert b'"dateTime":"2026-06-01T12:00:00-07:00"' in body
        assert b'"a@example.com"' in body
        assert dict(route.calls.last.request.url.params)["sendUpdates"] == "all"


@pytest.mark.asyncio
async def test_create_event_all_day_uses_date_field(gc: GoogleCalendar) -> None:
    """All-day event (10-char date-only string) maps to `date` field, not `dateTime`."""
    with respx.mock(base_url="https://www.googleapis.com/calendar/v3") as mock:
        route = mock.post("/calendars/primary/events").mock(
            return_value=httpx.Response(200, json={**_EVENT, "start": {"date": "2026-06-01"}})
        )
        await gc.acreate_event(summary="All-day", start="2026-06-01", end="2026-06-02")
        body = route.calls.last.request.read()
        # All-day events use the 'date' field, not 'dateTime'
        assert b'"date":"2026-06-01"' in body
        assert b'"dateTime"' not in body


@pytest.mark.asyncio
async def test_update_event_sends_only_changed_fields(gc: GoogleCalendar) -> None:
    """update_event uses PATCH semantics; only provided fields appear in body."""
    with respx.mock(base_url="https://www.googleapis.com/calendar/v3") as mock:
        route = mock.patch("/calendars/primary/events/evt-abc-123").mock(
            return_value=httpx.Response(200, json=_EVENT)
        )
        await gc.aupdate_event(
            event_id="evt-abc-123",
            summary="Updated title",
            location="New room",
        )
        body = route.calls.last.request.read()
        assert b'"summary":"Updated title"' in body
        assert b'"location":"New room"' in body
        # Unchanged fields don't appear
        assert b'"description"' not in body
        assert b'"start"' not in body
        assert b'"end"' not in body


@pytest.mark.asyncio
async def test_delete_event(gc: GoogleCalendar) -> None:
    """delete_event: DELETE /calendars/{id}/events/{eventId} → None."""
    with respx.mock(base_url="https://www.googleapis.com/calendar/v3") as mock:
        route = mock.delete("/calendars/primary/events/evt-abc-123").mock(
            return_value=httpx.Response(204)
        )
        result = await gc.adelete_event(event_id="evt-abc-123")
        assert result is None
        params = dict(route.calls.last.request.url.params)
        assert params["sendUpdates"] == "none"  # default


@pytest.mark.asyncio
async def test_list_event_instances_recurring_event(gc: GoogleCalendar) -> None:
    """list_event_instances: GET .../events/{eventId}/instances → bare list[CalendarEvent]."""
    with respx.mock(base_url="https://www.googleapis.com/calendar/v3") as mock:
        mock.get("/calendars/primary/events/recurring-abc/instances").mock(
            return_value=httpx.Response(
                200,
                json={"items": [_EVENT, {**_EVENT, "id": "evt-abc-124"}]},
            )
        )
        instances = await gc.alist_event_instances(calendar_id="primary", event_id="recurring-abc")
        # Returns a bare list, not a PaginatedList
        assert len(instances) == 2
        assert instances[0].id == "evt-abc-123"


@pytest.mark.asyncio
async def test_move_event(gc: GoogleCalendar) -> None:
    """move_event: POST /calendars/{src}/events/{eventId}/move?destination={dst}."""
    with respx.mock(base_url="https://www.googleapis.com/calendar/v3") as mock:
        route = mock.post("/calendars/primary/events/evt-abc-123/move").mock(
            return_value=httpx.Response(200, json=_EVENT)
        )
        moved = await gc.amove_event(
            calendar_id="primary",
            event_id="evt-abc-123",
            destination_calendar_id="cal-other",
        )
        assert moved.id == "evt-abc-123"
        params = dict(route.calls.last.request.url.params)
        assert params["destination"] == "cal-other"


@pytest.mark.asyncio
async def test_quick_add_event(gc: GoogleCalendar) -> None:
    """quick_add_event: POST .../events/quickAdd?text=…"""
    with respx.mock(base_url="https://www.googleapis.com/calendar/v3") as mock:
        route = mock.post("/calendars/primary/events/quickAdd").mock(
            return_value=httpx.Response(200, json=_EVENT)
        )
        evt = await gc.aquick_add_event(text="Lunch tomorrow 12pm")
        assert evt.id == "evt-abc-123"
        params = dict(route.calls.last.request.url.params)
        assert params["text"] == "Lunch tomorrow 12pm"


@pytest.mark.asyncio
async def test_list_calendars(gc: GoogleCalendar) -> None:
    """list_calendars: GET /users/me/calendarList → PaginatedList[Calendar]."""
    with respx.mock(base_url="https://www.googleapis.com/calendar/v3") as mock:
        mock.get("/users/me/calendarList").mock(
            return_value=httpx.Response(200, json={"items": [_CAL]})
        )
        page = await gc.alist_calendars()
        # Returns PaginatedList
        assert len(page.items) == 1
        assert page.items[0].id == "cal-abc"
        assert page.page_state.has_more is False


@pytest.mark.asyncio
async def test_create_calendar(gc: GoogleCalendar) -> None:
    """create_calendar: POST /calendars with summary + timeZone."""
    with respx.mock(base_url="https://www.googleapis.com/calendar/v3") as mock:
        route = mock.post("/calendars").mock(return_value=httpx.Response(200, json=_CAL))
        cal = await gc.acreate_calendar(
            summary="New Cal",
            description="desc",
            time_zone="UTC",
        )
        assert cal.id == "cal-abc"
        body = route.calls.last.request.read()
        assert b'"summary":"New Cal"' in body
        assert b'"timeZone":"UTC"' in body


@pytest.mark.asyncio
async def test_delete_calendar(gc: GoogleCalendar) -> None:
    """delete_calendar: DELETE /calendars/{id} → None."""
    with respx.mock(base_url="https://www.googleapis.com/calendar/v3") as mock:
        mock.delete("/calendars/cal-abc").mock(return_value=httpx.Response(204))
        result = await gc.adelete_calendar(calendar_id="cal-abc")
        assert result is None


@pytest.mark.asyncio
async def test_update_calendar_fetches_then_puts_full_body(gc: GoogleCalendar) -> None:
    """update_calendar: GET current → merge → PUT (full-body, Calendar API requires it)."""
    with respx.mock(base_url="https://www.googleapis.com/calendar/v3") as mock:
        mock.get("/calendars/cal-abc").mock(return_value=httpx.Response(200, json=_CAL))
        route = mock.put("/calendars/cal-abc").mock(
            return_value=httpx.Response(200, json={**_CAL, "summary": "Updated"})
        )
        result = await gc.aupdate_calendar(calendar_id="cal-abc", summary="Updated")
        assert result.summary == "Updated"
        body = route.calls.last.request.read()
        assert b'"summary":"Updated"' in body
        # PUT merged the unchanged description from the GET
        assert b'"description":"calendar description"' in body


@pytest.mark.asyncio
async def test_clear_calendar(gc: GoogleCalendar) -> None:
    """clear_calendar: POST /calendars/{id}/clear → None (only valid on primary calendars)."""
    with respx.mock(base_url="https://www.googleapis.com/calendar/v3") as mock:
        mock.post("/calendars/primary/clear").mock(return_value=httpx.Response(204))
        result = await gc.aclear_calendar(calendar_id="primary")
        assert result is None


@pytest.mark.asyncio
async def test_subscribe_calendar(gc: GoogleCalendar) -> None:
    """subscribe_calendar: POST /users/me/calendarList with {id} → Calendar."""
    with respx.mock(base_url="https://www.googleapis.com/calendar/v3") as mock:
        route = mock.post("/users/me/calendarList").mock(
            return_value=httpx.Response(200, json=_CAL)
        )
        cal = await gc.asubscribe_calendar(calendar_id="cal-public")
        assert cal.id == "cal-abc"
        body = route.calls.last.request.read()
        assert b'"id":"cal-public"' in body


@pytest.mark.asyncio
async def test_unsubscribe_calendar(gc: GoogleCalendar) -> None:
    """unsubscribe_calendar: DELETE /users/me/calendarList/{id} → None."""
    with respx.mock(base_url="https://www.googleapis.com/calendar/v3") as mock:
        mock.delete("/users/me/calendarList/cal-abc").mock(return_value=httpx.Response(204))
        result = await gc.aunsubscribe_calendar(calendar_id="cal-abc")
        assert result is None


@pytest.mark.asyncio
async def test_list_calendar_acl(gc: GoogleCalendar) -> None:
    """list_calendar_acl: GET /calendars/{id}/acl → list of CalendarACL."""
    with respx.mock(base_url="https://www.googleapis.com/calendar/v3") as mock:
        mock.get("/calendars/cal-abc/acl").mock(
            return_value=httpx.Response(200, json={"items": [_ACL]})
        )
        acls = await gc.alist_calendar_acl(calendar_id="cal-abc")
        assert len(acls) == 1


@pytest.mark.asyncio
async def test_add_calendar_acl(gc: GoogleCalendar) -> None:
    """add_calendar_acl: POST /calendars/{id}/acl with email + role.

    The connector hardcodes `scope.type = "user"` — only user-by-email
    rules are exposed; group/domain scopes are not (intentional API
    simplification).
    """
    with respx.mock(base_url="https://www.googleapis.com/calendar/v3") as mock:
        route = mock.post("/calendars/cal-abc/acl").mock(
            return_value=httpx.Response(200, json=_ACL)
        )
        acl = await gc.aadd_calendar_acl(
            calendar_id="cal-abc",
            email="alice@example.com",
            role="reader",
        )
        assert acl.id == "user:a@example.com"
        body = route.calls.last.request.read()
        assert b'"role":"reader"' in body
        assert b'"type":"user"' in body
        assert b'"value":"alice@example.com"' in body


@pytest.mark.asyncio
async def test_remove_calendar_acl(gc: GoogleCalendar) -> None:
    """remove_calendar_acl: DELETE /calendars/{id}/acl/{ruleId} → None."""
    with respx.mock(base_url="https://www.googleapis.com/calendar/v3") as mock:
        mock.delete("/calendars/cal-abc/acl/user%3Aalice%40example.com").mock(
            return_value=httpx.Response(204)
        )
        result = await gc.aremove_calendar_acl(
            calendar_id="cal-abc", rule_id="user:alice@example.com"
        )
        assert result is None


@pytest.mark.asyncio
async def test_get_free_busy(gc: GoogleCalendar) -> None:
    """get_free_busy: POST /freeBusy → list of FreeBusyCalendar with `busy` periods."""
    with respx.mock(base_url="https://www.googleapis.com/calendar/v3") as mock:
        route = mock.post("/freeBusy").mock(
            return_value=httpx.Response(
                200,
                json={
                    "calendars": {
                        "primary": {
                            "busy": [
                                {"start": "2026-06-01T10:00:00Z", "end": "2026-06-01T11:00:00Z"}
                            ]
                        }
                    }
                },
            )
        )
        busy = await gc.aget_free_busy(
            calendar_ids=["primary"],
            time_min="2026-06-01T00:00:00Z",
            time_max="2026-06-02T00:00:00Z",
        )
        assert len(busy) == 1
        assert busy[0].calendar_id == "primary"
        # Model exposes `.busy` (list of {start, end} dicts), not `.busy_periods`
        assert len(busy[0].busy) == 1
        body = route.calls.last.request.read()
        assert b'"items":[{"id":"primary"}]' in body


@pytest.mark.asyncio
async def test_get_colors(gc: GoogleCalendar) -> None:
    """get_colors: GET /colors → CalendarColors."""
    with respx.mock(base_url="https://www.googleapis.com/calendar/v3") as mock:
        mock.get("/colors").mock(
            return_value=httpx.Response(
                200,
                json={
                    "calendar": {"1": {"background": "#ac725e", "foreground": "#1d1d1d"}},
                    "event": {"1": {"background": "#a4bdfc", "foreground": "#1d1d1d"}},
                },
            )
        )
        colors = await gc.aget_colors()
        assert "1" in colors.calendar
        assert "1" in colors.event


# ===========================================================================
# Round 2 — defensive parsing + URL-path guards
# ===========================================================================


@pytest.mark.asyncio
async def test_calendar_id_with_slash_percent_encoded(gc: GoogleCalendar) -> None:
    """Adversarial calendar_id MUST NOT escape /calendars/ prefix."""
    with respx.mock(base_url="https://www.googleapis.com/calendar/v3") as mock:
        route = mock.get(host="www.googleapis.com").mock(
            return_value=httpx.Response(404, json={"error": {"code": 404, "message": "Not found"}})
        )
        with pytest.raises(NotFoundError):
            await gc.aget_event(event_id="x", calendar_id="../admin")

        url = str(route.calls.last.request.url)
        assert "/calendars/" in url
        assert "..%2Fadmin" in url or "..%2fadmin" in url
        assert "/admin/" not in url


@pytest.mark.asyncio
async def test_event_with_email_calendar_id(gc: GoogleCalendar) -> None:
    """Calendar IDs are commonly email addresses (e.g. alice@example.com).
    The `@` and `.` characters must round-trip correctly under percent-encoding."""
    with respx.mock(base_url="https://www.googleapis.com/calendar/v3") as mock:
        route = mock.get(host="www.googleapis.com").mock(
            return_value=httpx.Response(200, json=_EVENT)
        )
        await gc.aget_event(event_id="evt", calendar_id="alice@example.com")
        url = str(route.calls.last.request.url)
        # Either form acceptable
        assert "alice%40example.com" in url or "alice@example.com" in url


@pytest.mark.asyncio
async def test_event_model_tolerates_unknown_fields(gc: GoogleCalendar) -> None:
    """Real Calendar API responses include many fields we don't model
    (kind, etag, sequence, iCalUID, transparency, etc.). extra='ignore'
    on the model silently drops them."""
    fat = {
        **_EVENT,
        "kind": "calendar#event",
        "etag": "etag-1",
        "iCalUID": "abc@google.com",
        "sequence": 0,
        "transparency": "opaque",
        "visibility": "default",
        "reminders": {"useDefault": True},
        "eventType": "default",
    }
    with respx.mock(base_url="https://www.googleapis.com/calendar/v3") as mock:
        mock.get("/calendars/primary/events/evt-abc-123").mock(
            return_value=httpx.Response(200, json=fat)
        )
        evt = await gc.aget_event(event_id="evt-abc-123")
        assert evt.id == "evt-abc-123"
        assert evt.summary == "Test Event"


@pytest.mark.asyncio
async def test_recurring_event_parses_recurrence_rules(gc: GoogleCalendar) -> None:
    """Recurring events return a `recurrence` list with RRULE strings."""
    recurring = {
        **_EVENT,
        "id": "evt-rec",
        "recurrence": ["RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR"],
        "recurringEventId": None,
    }
    with respx.mock(base_url="https://www.googleapis.com/calendar/v3") as mock:
        mock.get("/calendars/primary/events/evt-rec").mock(
            return_value=httpx.Response(200, json=recurring)
        )
        evt = await gc.aget_event(event_id="evt-rec")
        assert evt.recurrence == ["RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR"]


@pytest.mark.asyncio
async def test_max_results_clamped_to_2500(gc: GoogleCalendar) -> None:
    """Per the Calendar API spec, max_results > 2500 must be clamped."""
    with respx.mock(base_url="https://www.googleapis.com/calendar/v3") as mock:
        route = mock.get("/calendars/primary/events").mock(
            return_value=httpx.Response(200, json={"items": []})
        )
        await gc.alist_events(max_results=10000)
        assert dict(route.calls.last.request.url.params)["maxResults"] == "2500"


# ===========================================================================
# Round 3 — error matrix
# ===========================================================================


@pytest.mark.asyncio
async def test_401_raises_invalid_credentials(gc: GoogleCalendar) -> None:
    with respx.mock(base_url="https://www.googleapis.com/calendar/v3") as mock:
        mock.get("/calendars/primary/events/x").mock(
            return_value=httpx.Response(
                401, json={"error": {"code": 401, "message": "Invalid Credentials"}}
            )
        )
        with pytest.raises(InvalidCredentialsError) as exc_info:
            await gc.aget_event(event_id="x")
        assert exc_info.value.connector == "gcalendar"


@pytest.mark.asyncio
async def test_403_raises_permission_denied(gc: GoogleCalendar) -> None:
    with respx.mock(base_url="https://www.googleapis.com/calendar/v3") as mock:
        mock.get("/calendars/primary/events/x").mock(
            return_value=httpx.Response(
                403, json={"error": {"code": 403, "message": "Insufficient Permission"}}
            )
        )
        with pytest.raises(PermissionDeniedError):
            await gc.aget_event(event_id="x")


@pytest.mark.asyncio
async def test_404_raises_not_found(gc: GoogleCalendar) -> None:
    with respx.mock(base_url="https://www.googleapis.com/calendar/v3") as mock:
        mock.get("/calendars/primary/events/missing").mock(
            return_value=httpx.Response(404, json={"error": {"code": 404, "message": "Not Found"}})
        )
        with pytest.raises(NotFoundError):
            await gc.aget_event(event_id="missing")


@pytest.mark.asyncio
async def test_410_gone_raises_api_error(gc: GoogleCalendar) -> None:
    """410 Gone is returned for deleted events. Falls through to APIError
    (the framework helper doesn't have a special 410 mapping)."""
    from toolsconnector.errors import APIError

    with respx.mock(base_url="https://www.googleapis.com/calendar/v3") as mock:
        mock.get("/calendars/primary/events/gone").mock(
            return_value=httpx.Response(
                410, json={"error": {"code": 410, "message": "Resource has been deleted"}}
            )
        )
        with pytest.raises(APIError):
            await gc.aget_event(event_id="gone")


@pytest.mark.asyncio
async def test_429_raises_rate_limit(gc: GoogleCalendar) -> None:
    with respx.mock(base_url="https://www.googleapis.com/calendar/v3") as mock:
        mock.get("/calendars/primary/events/x").mock(
            return_value=httpx.Response(
                429,
                json={"error": {"code": 429, "message": "Quota exceeded"}},
                headers={"Retry-After": "30"},
            )
        )
        with pytest.raises(RateLimitError):
            await gc.aget_event(event_id="x")


@pytest.mark.asyncio
async def test_500_raises_server_error(gc: GoogleCalendar) -> None:
    with respx.mock(base_url="https://www.googleapis.com/calendar/v3") as mock:
        mock.get("/calendars/primary/events/x").mock(
            return_value=httpx.Response(500, json={"error": {"code": 500}})
        )
        with pytest.raises(ServerError):
            await gc.aget_event(event_id="x")


# ===========================================================================
# Round 4 — transport errors + 204 handling
# ===========================================================================


@pytest.mark.asyncio
async def test_connect_error_typed(gc: GoogleCalendar) -> None:
    with respx.mock(base_url="https://www.googleapis.com/calendar/v3") as mock:
        mock.get("/calendars/primary/events/x").mock(side_effect=httpx.ConnectError("DNS"))
        with pytest.raises(TCConnectionError):
            await gc.aget_event(event_id="x")


@pytest.mark.asyncio
async def test_timeout_typed(gc: GoogleCalendar) -> None:
    with respx.mock(base_url="https://www.googleapis.com/calendar/v3") as mock:
        mock.get("/calendars/primary/events/x").mock(side_effect=httpx.ReadTimeout("slow"))
        with pytest.raises(TCTimeoutError):
            await gc.aget_event(event_id="x")


@pytest.mark.asyncio
async def test_transport_error_typed(gc: GoogleCalendar) -> None:
    with respx.mock(base_url="https://www.googleapis.com/calendar/v3") as mock:
        mock.get("/calendars/primary/events/x").mock(
            side_effect=httpx.RemoteProtocolError("dropped")
        )
        with pytest.raises(TCTransportError):
            await gc.aget_event(event_id="x")


# ===========================================================================
# Round 5 — MCP exposure + dangerous flag + sync wrappers + concurrency
# ===========================================================================


def test_dangerous_actions_flagged() -> None:
    """Writes/mutations are dangerous; reads + move_event are not.

    `move_event` is intentionally NOT flagged dangerous — moving an
    event between calendars preserves the data, just relocates it.
    The connector author treats it as a re-attribution rather than
    destructive mutation.
    """
    spec = GoogleCalendar.get_spec()
    expected_dangerous = {
        "create_event",
        "update_event",
        "delete_event",
        "create_calendar",
        "update_calendar",
        "delete_calendar",
        "clear_calendar",
        "subscribe_calendar",
        "unsubscribe_calendar",
        "add_calendar_acl",
        "remove_calendar_acl",
        "quick_add_event",
    }
    for a in expected_dangerous:
        assert spec.actions[a].dangerous is True, f"{a} must be dangerous=True"
    expected_safe = {
        "list_events",
        "get_event",
        "list_event_instances",
        "list_calendars",
        "list_calendar_acl",
        "get_free_busy",
        "get_colors",
        "move_event",
    }
    for a in expected_safe:
        assert spec.actions[a].dangerous is False, f"{a} must be dangerous=False"


def test_openai_schema_sweep() -> None:
    from toolsconnector.serve import ToolKit

    kit = ToolKit(["gcalendar"], credentials={"gcalendar": "ya29.fake"})
    tools = kit.to_openai_tools()
    assert len(tools) == 20
    for tool in tools:
        assert tool["function"]["name"].startswith("gcalendar_")


def test_mcp_exposure_all_actions() -> None:
    from toolsconnector.serve import ToolKit

    kit = ToolKit(["gcalendar"], credentials={"gcalendar": "ya29.fake"})
    names = {t["name"] for t in kit.list_tools()}
    assert len(names) == 20


def test_mcp_exclude_dangerous_filters_12_dangerous() -> None:
    """12 dangerous filtered → 8 safe remain (incl. move_event which is
    safe-by-flag despite mutating where an event lives)."""
    from toolsconnector.serve import ToolKit

    kit_safe = ToolKit(
        ["gcalendar"], credentials={"gcalendar": "ya29.fake"}, exclude_dangerous=True
    )
    tools = kit_safe.list_tools()
    assert len(tools) == 8


def test_sync_wrappers_exist() -> None:
    inst = GoogleCalendar(credentials="ya29.fake")
    for action_name in (
        "list_events",
        "get_event",
        "create_event",
        "delete_event",
        "create_calendar",
        "get_free_busy",
        "get_colors",
    ):
        assert hasattr(inst, action_name)
        assert hasattr(inst, f"a{action_name}")


def test_verification_status_live() -> None:
    assert GoogleCalendar.verification_status == "live"
    assert GoogleCalendar.get_spec().verification_status == "live"


@pytest.mark.asyncio
async def test_concurrent_requests_safe(gc: GoogleCalendar) -> None:
    with respx.mock(base_url="https://www.googleapis.com/calendar/v3") as mock:
        mock.get("/calendars/primary/events/a").mock(
            return_value=httpx.Response(200, json={**_EVENT, "id": "a"})
        )
        mock.get("/calendars/primary/events/b").mock(
            return_value=httpx.Response(200, json={**_EVENT, "id": "b"})
        )
        results = await asyncio.gather(
            gc.aget_event(event_id="a"),
            gc.aget_event(event_id="b"),
        )
        assert results[0].id == "a"
        assert results[1].id == "b"
