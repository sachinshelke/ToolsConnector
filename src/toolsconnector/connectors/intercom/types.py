"""Pydantic models for Intercom connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class IntercomContact(BaseModel):
    """An Intercom contact (user or lead)."""

    model_config = ConfigDict(frozen=True)

    id: str
    type: str = "contact"
    role: str = "user"
    email: Optional[str] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    external_id: Optional[str] = None
    avatar: Optional[str] = None
    owner_id: Optional[int] = None
    signed_up_at: Optional[int] = None
    last_seen_at: Optional[int] = None
    created_at: Optional[int] = None
    updated_at: Optional[int] = None
    unsubscribed_from_emails: bool = False
    has_hard_bounced: bool = False
    custom_attributes: dict[str, Any] = Field(default_factory=dict)
    tags: list[dict[str, Any]] = Field(default_factory=list)
    location: Optional[dict[str, Any]] = None


class IntercomConversation(BaseModel):
    """An Intercom conversation thread."""

    model_config = ConfigDict(frozen=True)

    id: str
    type: str = "conversation"
    title: Optional[str] = None
    state: str = "open"
    read: bool = False
    priority: str = "not_priority"
    admin_assignee_id: Optional[int] = None
    team_assignee_id: Optional[str] = None
    created_at: Optional[int] = None
    updated_at: Optional[int] = None
    waiting_since: Optional[int] = None
    snoozed_until: Optional[int] = None
    open: bool = True
    tags: list[dict[str, Any]] = Field(default_factory=list)
    source: Optional[dict[str, Any]] = None
    contacts: list[dict[str, Any]] = Field(default_factory=list)
    statistics: Optional[dict[str, Any]] = None


class IntercomMessage(BaseModel):
    """An Intercom message (in-app or email)."""

    model_config = ConfigDict(frozen=True)

    id: str
    type: str = "admin_message"
    message_type: str = "email"
    subject: Optional[str] = None
    body: str = ""
    created_at: Optional[int] = None
    owner: Optional[dict[str, Any]] = None


class IntercomAdmin(BaseModel):
    """An Intercom workspace admin/operator."""

    model_config = ConfigDict(frozen=True)

    id: str
    type: str = "admin"
    name: Optional[str] = None
    email: Optional[str] = None
    job_title: Optional[str] = None
    has_inbox_seat: bool = False
    avatar: Optional[str] = None


class IntercomTag(BaseModel):
    """An Intercom tag."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str = ""
    type: str = "tag"
    applied_count: Optional[int] = None


class IntercomCompany(BaseModel):
    """An Intercom company (organization)."""

    model_config = ConfigDict(frozen=True)

    id: str
    type: str = "company"
    name: Optional[str] = None
    company_id: Optional[str] = None
    plan: Optional[str] = None
    size: Optional[int] = None
    website: Optional[str] = None
    industry: Optional[str] = None
    monthly_spend: Optional[float] = None
    session_count: Optional[int] = None
    user_count: Optional[int] = None
    remote_created_at: Optional[int] = None
    created_at: Optional[int] = None
    updated_at: Optional[int] = None
    custom_attributes: dict[str, Any] = Field(default_factory=dict)


class IntercomSegment(BaseModel):
    """An Intercom segment (saved filter)."""

    model_config = ConfigDict(frozen=True)

    id: str
    type: str = "segment"
    name: str = ""
    count: Optional[int] = None
    person_type: str = "user"
    created_at: Optional[int] = None
    updated_at: Optional[int] = None
