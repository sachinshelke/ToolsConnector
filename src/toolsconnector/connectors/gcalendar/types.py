"""Pydantic models for Google Calendar connector types.

All response models use ``frozen=True`` to enforce immutability.
Input-only models (used as parameters) are left mutable.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Embedded models
# ---------------------------------------------------------------------------


class EventTime(BaseModel):
    """A datetime or date for calendar events.

    Google Calendar events use either ``dateTime`` (for timed events)
    or ``date`` (for all-day events), plus an optional ``timeZone``.
    """

    model_config = ConfigDict(frozen=True)

    date_time: Optional[str] = None
    date: Optional[str] = None
    time_zone: Optional[str] = None


class EventAttendee(BaseModel):
    """An attendee on a calendar event."""

    model_config = ConfigDict(frozen=True)

    email: str
    display_name: Optional[str] = None
    response_status: str = "needsAction"
    optional: bool = False
    organizer: bool = False
    self_: bool = Field(default=False, alias="self")

    model_config = ConfigDict(frozen=True, populate_by_name=True)


class EventReminder(BaseModel):
    """A reminder override on an event."""

    model_config = ConfigDict(frozen=True)

    method: str = "popup"  # "email" or "popup"
    minutes: int = 10


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class CalendarEvent(BaseModel):
    """A Google Calendar event."""

    model_config = ConfigDict(frozen=True)

    id: str
    summary: str = ""
    description: Optional[str] = None
    location: Optional[str] = None
    start: Optional[EventTime] = None
    end: Optional[EventTime] = None
    status: str = "confirmed"
    html_link: Optional[str] = None
    created: Optional[str] = None
    updated: Optional[str] = None
    creator_email: Optional[str] = None
    organizer_email: Optional[str] = None
    attendees: list[EventAttendee] = Field(default_factory=list)
    recurrence: list[str] = Field(default_factory=list)
    recurring_event_id: Optional[str] = None
    calendar_id: Optional[str] = None
    color_id: Optional[str] = None
    hangout_link: Optional[str] = None
    conference_link: Optional[str] = None


class Calendar(BaseModel):
    """A Google Calendar."""

    model_config = ConfigDict(frozen=True)

    id: str
    summary: str = ""
    description: Optional[str] = None
    time_zone: Optional[str] = None
    color_id: Optional[str] = None
    background_color: Optional[str] = None
    foreground_color: Optional[str] = None
    selected: bool = True
    primary: bool = False
    access_role: str = "reader"


class EventId(BaseModel):
    """Result of creating or updating an event."""

    model_config = ConfigDict(frozen=True)

    id: str
    html_link: Optional[str] = None
    status: str = "confirmed"


class FreeBusyCalendar(BaseModel):
    """Free/busy information for a single calendar."""

    model_config = ConfigDict(frozen=True)

    calendar_id: str = ""
    busy: list[dict[str, str]] = Field(default_factory=list)
    errors: list[dict[str, str]] = Field(default_factory=list)
