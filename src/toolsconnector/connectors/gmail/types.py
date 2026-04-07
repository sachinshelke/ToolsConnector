"""Pydantic models for Gmail connector types.

All response models use ``frozen=True`` to enforce immutability.
Input-only models (used as parameters) are left mutable.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Shared / embedded models
# ---------------------------------------------------------------------------


class EmailAddress(BaseModel):
    """An email address with optional display name."""

    model_config = ConfigDict(frozen=True)

    email: str
    name: Optional[str] = None


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class EmailHeader(BaseModel):
    """Email header metadata (lightweight list representation)."""

    model_config = ConfigDict(frozen=True)

    message_id: str
    thread_id: str
    subject: str
    from_address: EmailAddress
    to: list[EmailAddress]
    cc: list[EmailAddress] = Field(default_factory=list)
    bcc: list[EmailAddress] = Field(default_factory=list)
    date: str  # ISO 8601 datetime
    snippet: str = ""
    labels: list[str] = Field(default_factory=list)
    has_attachments: bool = False


class Email(BaseModel):
    """Full email message."""

    model_config = ConfigDict(frozen=True)

    id: str
    thread_id: str
    subject: str
    from_address: Optional[EmailAddress] = None
    to: list[EmailAddress] = Field(default_factory=list)
    cc: list[EmailAddress] = Field(default_factory=list)
    date: Optional[str] = None  # ISO 8601 datetime
    snippet: str = ""
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    labels: list[str] = Field(default_factory=list)
    has_attachments: bool = False


class Label(BaseModel):
    """Gmail label."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    type: str = "user"
    messages_total: int = 0
    messages_unread: int = 0


class MessageId(BaseModel):
    """Result of sending/creating a message."""

    model_config = ConfigDict(frozen=True)

    id: str
    thread_id: Optional[str] = None


class DraftId(BaseModel):
    """Result of creating a draft."""

    model_config = ConfigDict(frozen=True)

    id: str
    message_id: Optional[str] = None


class Attachment(BaseModel):
    """Email attachment metadata and optional data."""

    model_config = ConfigDict(frozen=True)

    id: str
    filename: str
    mime_type: str
    size: int = 0
    data: Optional[str] = None  # base64-encoded attachment data


class Thread(BaseModel):
    """Gmail conversation thread."""

    model_config = ConfigDict(frozen=True)

    id: str
    snippet: str = ""
    history_id: Optional[str] = None
    messages_count: int = 0


class LabelColor(BaseModel):
    """Gmail label color specification."""

    model_config = ConfigDict(frozen=True)

    text_color: Optional[str] = None
    background_color: Optional[str] = None


class Draft(BaseModel):
    """Gmail draft with its associated message."""

    model_config = ConfigDict(frozen=True)

    id: str
    message: Optional[Email] = None


class UserProfile(BaseModel):
    """Gmail user profile information."""

    model_config = ConfigDict(frozen=True)

    email_address: str
    messages_total: int = 0
    threads_total: int = 0
    history_id: str = ""


class HistoryRecord(BaseModel):
    """Gmail history record for incremental sync.

    Each record represents a change event identified by a unique
    history ID. The optional lists contain message IDs affected by
    the corresponding change type.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    messages_added: list[str] = Field(default_factory=list)
    messages_deleted: list[str] = Field(default_factory=list)
    labels_added: list[str] = Field(default_factory=list)
    labels_removed: list[str] = Field(default_factory=list)


class VacationSettings(BaseModel):
    """Gmail vacation auto-reply settings."""

    model_config = ConfigDict(frozen=True)

    enable_auto_reply: bool = False
    response_subject: Optional[str] = None
    response_body_plain_text: Optional[str] = None
    response_body_html: Optional[str] = None
    start_time: Optional[str] = None  # epoch millis as string
    end_time: Optional[str] = None  # epoch millis as string
