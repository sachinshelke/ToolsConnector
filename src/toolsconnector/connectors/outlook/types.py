"""Pydantic models for the Microsoft Outlook (MS Graph) connector.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Shared / embedded models
# ---------------------------------------------------------------------------


class EmailRecipient(BaseModel):
    """An email recipient with address and optional display name."""

    model_config = ConfigDict(frozen=True)

    email: str
    name: Optional[str] = None


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class OutlookMessage(BaseModel):
    """A single Outlook email message from the MS Graph API."""

    model_config = ConfigDict(frozen=True)

    id: str
    subject: Optional[str] = None
    body_preview: Optional[str] = None
    body_content: Optional[str] = None
    body_content_type: Optional[str] = None
    from_address: Optional[EmailRecipient] = None
    to_recipients: list[EmailRecipient] = Field(default_factory=list)
    cc_recipients: list[EmailRecipient] = Field(default_factory=list)
    received_datetime: Optional[str] = None
    sent_datetime: Optional[str] = None
    is_read: bool = False
    has_attachments: bool = False
    importance: str = "normal"
    conversation_id: Optional[str] = None
    web_link: Optional[str] = None


class MailFolder(BaseModel):
    """A mail folder (Inbox, Sent Items, custom folders, etc.)."""

    model_config = ConfigDict(frozen=True)

    id: str
    display_name: str
    parent_folder_id: Optional[str] = None
    child_folder_count: int = 0
    total_item_count: int = 0
    unread_item_count: int = 0


class OutlookMessageId(BaseModel):
    """Lightweight result returned after sending or creating a draft."""

    model_config = ConfigDict(frozen=True)

    id: str
