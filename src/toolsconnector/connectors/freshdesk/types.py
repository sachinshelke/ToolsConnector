"""Pydantic models for Freshdesk connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class FreshdeskTicket(BaseModel):
    """A Freshdesk support ticket."""

    model_config = ConfigDict(frozen=True)

    id: int
    subject: str = ""
    description: Optional[str] = None
    description_text: Optional[str] = None
    status: int = 2
    priority: int = 1
    type: Optional[str] = None
    requester_id: Optional[int] = None
    responder_id: Optional[int] = None
    group_id: Optional[int] = None
    source: int = 0
    email: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    cc_emails: list[str] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    due_by: Optional[str] = None

    @property
    def status_label(self) -> str:
        """Human-readable status label."""
        mapping = {2: "Open", 3: "Pending", 4: "Resolved", 5: "Closed"}
        return mapping.get(self.status, f"Unknown({self.status})")

    @property
    def priority_label(self) -> str:
        """Human-readable priority label."""
        mapping = {1: "Low", 2: "Medium", 3: "High", 4: "Urgent"}
        return mapping.get(self.priority, f"Unknown({self.priority})")


class FreshdeskContact(BaseModel):
    """A Freshdesk contact."""

    model_config = ConfigDict(frozen=True)

    id: int
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    company_id: Optional[int] = None
    active: bool = True
    address: Optional[str] = None
    job_title: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class FreshdeskReply(BaseModel):
    """A Freshdesk ticket reply / conversation entry."""

    model_config = ConfigDict(frozen=True)

    id: int
    body: str = ""
    body_text: Optional[str] = None
    user_id: Optional[int] = None
    ticket_id: Optional[int] = None
    incoming: bool = False
    private: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    attachments: list[Any] = Field(default_factory=list)
