"""Pydantic models for Calendly connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class CalendlyUser(BaseModel):
    """A Calendly user (the authenticated account)."""

    model_config = ConfigDict(frozen=True)

    uri: str
    name: str = ""
    email: Optional[str] = None
    slug: Optional[str] = None
    scheduling_url: Optional[str] = None
    timezone: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    current_organization: Optional[str] = None


class CalendlyEventType(BaseModel):
    """A Calendly event type (meeting template)."""

    model_config = ConfigDict(frozen=True)

    uri: str
    name: str = ""
    slug: Optional[str] = None
    active: bool = True
    kind: Optional[str] = None
    scheduling_url: Optional[str] = None
    duration: Optional[int] = None
    type: Optional[str] = None
    color: Optional[str] = None
    description_plain: Optional[str] = None
    description_html: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class CalendlyEvent(BaseModel):
    """A Calendly scheduled event (meeting instance)."""

    model_config = ConfigDict(frozen=True)

    uri: str
    name: str = ""
    status: str = "active"
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    event_type: Optional[str] = None
    location: Optional[dict[str, Any]] = None
    invitees_counter: Optional[dict[str, int]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    event_memberships: list[dict[str, str]] = Field(default_factory=list)
    cancellation: Optional[dict[str, Any]] = None


class CalendlyInvitee(BaseModel):
    """An invitee of a Calendly scheduled event."""

    model_config = ConfigDict(frozen=True)

    uri: str
    name: str = ""
    email: Optional[str] = None
    status: str = "active"
    timezone: Optional[str] = None
    event: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    canceled: bool = False
    cancellation: Optional[dict[str, Any]] = None
    questions_and_answers: list[dict[str, Any]] = Field(default_factory=list)


class CalendlyWebhook(BaseModel):
    """A Calendly webhook subscription."""

    model_config = ConfigDict(frozen=True)

    uri: str
    callback_url: str = ""
    state: str = "active"
    events: list[str] = Field(default_factory=list)
    scope: str = "user"
    organization: Optional[str] = None
    user: Optional[str] = None
    creator: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
