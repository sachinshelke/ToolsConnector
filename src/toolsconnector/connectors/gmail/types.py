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


# ---------------------------------------------------------------------------
# Settings — Filters (users.settings.filters)
# ---------------------------------------------------------------------------


class FilterCriteria(BaseModel):
    """Match criteria for a Gmail filter.

    All fields optional; filters match when ALL specified criteria hold.
    See https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.settings.filters
    """

    model_config = ConfigDict(frozen=True)

    from_address: Optional[str] = None  # maps to API field `from`
    to: Optional[str] = None
    subject: Optional[str] = None
    query: Optional[str] = None  # same syntax as Gmail search box
    negated_query: Optional[str] = None  # `-(...)` to exclude
    has_attachment: Optional[bool] = None
    exclude_chats: Optional[bool] = None
    size: Optional[int] = None  # bytes
    size_comparison: Optional[str] = None  # "larger" | "smaller"


class FilterAction(BaseModel):
    """Actions applied to messages matching a filter."""

    model_config = ConfigDict(frozen=True)

    add_label_ids: list[str] = Field(default_factory=list)
    remove_label_ids: list[str] = Field(default_factory=list)
    forward: Optional[str] = None  # forwarding address


class Filter(BaseModel):
    """A Gmail filter (auto-categorization rule)."""

    model_config = ConfigDict(frozen=True)

    id: str
    criteria: FilterCriteria
    action: FilterAction


# ---------------------------------------------------------------------------
# Settings — Send-As addresses (users.settings.sendAs)
# ---------------------------------------------------------------------------


class SendAs(BaseModel):
    """A send-as alias — an address the user can send email from.

    Includes both owned primary addresses and verified aliases.
    See https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.settings.sendAs
    """

    model_config = ConfigDict(frozen=True)

    send_as_email: str
    display_name: Optional[str] = None
    reply_to_address: Optional[str] = None
    signature: Optional[str] = None
    is_primary: bool = False
    is_default: bool = False
    treat_as_alias: bool = False
    verification_status: Optional[str] = None  # "accepted" | "pending" | etc.
    # SMTP relay config for non-Gmail aliases (rare — advanced setups)
    smtp_msa_host: Optional[str] = None
    smtp_msa_port: Optional[int] = None
    smtp_msa_username: Optional[str] = None
    smtp_msa_security_mode: Optional[str] = None  # "smtpMsaSecurityMode" enum


# ---------------------------------------------------------------------------
# Settings — Delegates (users.settings.delegates)
# ---------------------------------------------------------------------------


class Delegate(BaseModel):
    """A delegate: another account with access to this mailbox.

    Workspace-only feature.
    See https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.settings.delegates
    """

    model_config = ConfigDict(frozen=True)

    delegate_email: str
    verification_status: Optional[str] = None  # "accepted" | "pending" | "rejected" | "expired"


# ---------------------------------------------------------------------------
# Settings — Forwarding addresses (users.settings.forwardingAddresses)
# ---------------------------------------------------------------------------


class ForwardingAddress(BaseModel):
    """A verified forwarding address.

    Separate from sendAs — forwarding routes incoming mail elsewhere.
    See https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.settings.forwardingAddresses
    """

    model_config = ConfigDict(frozen=True)

    forwarding_email: str
    verification_status: Optional[str] = None  # "accepted" | "pending"


# ---------------------------------------------------------------------------
# Settings — Misc (autoForwarding, imap, pop, language)
# ---------------------------------------------------------------------------


class AutoForwarding(BaseModel):
    """Top-level auto-forwarding configuration.

    Separate from per-address forwarding in filters — this forwards ALL
    incoming mail to a single address.
    """

    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    email_address: Optional[str] = None  # destination
    disposition: Optional[str] = None  # "leaveInInbox"|"archive"|"trash"|"markRead"


class ImapSettings(BaseModel):
    """IMAP access configuration for the mailbox."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    auto_expunge: bool = True
    expunge_behavior: Optional[str] = None  # "archive"|"trash"|"deleteForever"
    max_folder_size: int = 0  # 0 = unlimited


class PopSettings(BaseModel):
    """POP access configuration for the mailbox."""

    model_config = ConfigDict(frozen=True)

    access_window: Optional[str] = None  # "disabled"|"allMail"|"fromNowOn"
    disposition: Optional[str] = None  # "leaveInInbox"|"archive"|"trash"|"markRead"


class LanguageSettings(BaseModel):
    """Language preference for the Gmail UI."""

    model_config = ConfigDict(frozen=True)

    display_language: str  # BCP-47 code e.g. "en-US"
