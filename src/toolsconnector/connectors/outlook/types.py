"""Pydantic models for the Microsoft Outlook (MS Graph) connector.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

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


# ---------------------------------------------------------------------------
# Contact models
# ---------------------------------------------------------------------------


class OutlookContact(BaseModel):
    """An Outlook contact from the MS Graph People/Contacts API."""

    model_config = ConfigDict(frozen=True)

    id: str
    given_name: Optional[str] = None
    surname: Optional[str] = None
    display_name: Optional[str] = None
    email_addresses: list[dict[str, Optional[str]]] = Field(default_factory=list)
    phone_numbers: list[dict[str, Optional[str]]] = Field(default_factory=list)
    company_name: Optional[str] = None
    job_title: Optional[str] = None
    created_datetime: Optional[str] = None
    last_modified_datetime: Optional[str] = None


# ---------------------------------------------------------------------------
# Calendar models
# ---------------------------------------------------------------------------


class OutlookAttachment(BaseModel):
    """An attachment on an Outlook email message."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: Optional[str] = None
    content_type: Optional[str] = None
    size: int = 0
    is_inline: bool = False
    last_modified_datetime: Optional[str] = None
    content_id: Optional[str] = None
    content_bytes: Optional[str] = None


class MailRule(BaseModel):
    """An Inbox message rule from the MS Graph mailFolders messageRules API."""

    model_config = ConfigDict(frozen=True)

    id: str
    display_name: Optional[str] = None
    sequence: int = 0
    is_enabled: bool = True
    conditions: Optional[dict[str, Any]] = None
    actions: Optional[dict[str, Any]] = None
    exceptions: Optional[dict[str, Any]] = None
    has_error: bool = False
    is_read_only: bool = False


class OutlookCategory(BaseModel):
    """A master category defined in the user's Outlook mailbox."""

    model_config = ConfigDict(frozen=True)

    id: str
    display_name: str
    color: Optional[str] = None


class MailTip(BaseModel):
    """Mail tips for a recipient email address."""

    model_config = ConfigDict(frozen=True)

    email_address: Optional[str] = None
    automatic_replies: Optional[dict[str, Any]] = None
    mailbox_full: bool = False
    max_message_size: Optional[int] = None
    is_moderated: bool = False
    delivery_restricted: bool = False
    external_member_count: Optional[int] = None
    total_member_count: Optional[int] = None


class OutlookCalendarEvent(BaseModel):
    """An Outlook calendar event from the MS Graph Calendar API."""

    model_config = ConfigDict(frozen=True)

    id: str
    subject: Optional[str] = None
    body_preview: Optional[str] = None
    body_content: Optional[str] = None
    start_datetime: Optional[str] = None
    start_timezone: Optional[str] = None
    end_datetime: Optional[str] = None
    end_timezone: Optional[str] = None
    location: Optional[str] = None
    is_all_day: bool = False
    is_cancelled: bool = False
    organizer_name: Optional[str] = None
    organizer_email: Optional[str] = None
    attendees: list[dict[str, Optional[str]]] = Field(default_factory=list)
    web_link: Optional[str] = None
    created_datetime: Optional[str] = None
    last_modified_datetime: Optional[str] = None
