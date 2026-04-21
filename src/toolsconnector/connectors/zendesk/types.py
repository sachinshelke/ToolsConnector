"""Pydantic models for Zendesk connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ZendeskUser(BaseModel):
    """A Zendesk user (agent, end-user, or admin)."""

    model_config = ConfigDict(frozen=True)

    id: int
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    active: bool = True
    verified: bool = False
    phone: Optional[str] = None
    organization_id: Optional[int] = None
    time_zone: Optional[str] = None
    locale: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    url: Optional[str] = None


class ZendeskComment(BaseModel):
    """A comment on a Zendesk ticket."""

    model_config = ConfigDict(frozen=True)

    id: int
    type: Optional[str] = None
    body: Optional[str] = None
    html_body: Optional[str] = None
    plain_body: Optional[str] = None
    public: bool = True
    author_id: Optional[int] = None
    created_at: Optional[str] = None


class ZendeskTicket(BaseModel):
    """A Zendesk support ticket."""

    model_config = ConfigDict(frozen=True)

    id: int
    subject: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    type: Optional[str] = None
    requester_id: Optional[int] = None
    submitter_id: Optional[int] = None
    assignee_id: Optional[int] = None
    organization_id: Optional[int] = None
    group_id: Optional[int] = None
    tags: list[str] = Field(default_factory=list)
    via_channel: Optional[str] = None
    url: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ZendeskSearchResult(BaseModel):
    """A single Zendesk search result."""

    model_config = ConfigDict(frozen=True)

    id: int
    result_type: Optional[str] = None
    url: Optional[str] = None
    subject: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ZendeskGroup(BaseModel):
    """A Zendesk group (agent group)."""

    model_config = ConfigDict(frozen=True)

    id: int
    name: Optional[str] = None
    description: Optional[str] = None
    default: bool = False
    deleted: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ZendeskOrganization(BaseModel):
    """A Zendesk organization."""

    model_config = ConfigDict(frozen=True)

    id: int
    name: Optional[str] = None
    details: Optional[str] = None
    notes: Optional[str] = None
    group_id: Optional[int] = None
    domain_names: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    shared_tickets: bool = False
    shared_comments: bool = False
    external_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
