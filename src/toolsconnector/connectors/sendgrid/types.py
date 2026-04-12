"""Pydantic models for SendGrid connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class SendGridResponse(BaseModel):
    """Response from the SendGrid mail/send endpoint."""

    model_config = ConfigDict(frozen=True)

    status_code: int = 202
    message: str = "Email accepted for delivery"
    message_id: Optional[str] = None


class SendGridContact(BaseModel):
    """A SendGrid Marketing contact."""

    model_config = ConfigDict(frozen=True)

    id: Optional[str] = None
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_number: Optional[str] = None
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    city: Optional[str] = None
    state_province_region: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    alternate_emails: list[str] = Field(default_factory=list)
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    list_ids: list[str] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class SendGridJobId(BaseModel):
    """Job ID returned by asynchronous SendGrid operations."""

    model_config = ConfigDict(frozen=True)

    job_id: str


class SendGridList(BaseModel):
    """A SendGrid contact list."""

    model_config = ConfigDict(frozen=True)

    id: Optional[str] = None
    name: Optional[str] = None
    contact_count: int = 0
    sample_contacts: list[dict[str, Any]] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class SendGridStatMetrics(BaseModel):
    """Metrics within a SendGrid stat entry."""

    model_config = ConfigDict(frozen=True)

    blocks: int = 0
    bounce_drops: int = 0
    bounces: int = 0
    clicks: int = 0
    deferred: int = 0
    delivered: int = 0
    invalid_emails: int = 0
    opens: int = 0
    processed: int = 0
    requests: int = 0
    spam_report_drops: int = 0
    spam_reports: int = 0
    unique_clicks: int = 0
    unique_opens: int = 0
    unsubscribe_drops: int = 0
    unsubscribes: int = 0


class SendGridStat(BaseModel):
    """A single day's email statistics from SendGrid."""

    model_config = ConfigDict(frozen=True)

    date: Optional[str] = None
    stats: list[dict[str, Any]] = Field(default_factory=list)


class SendGridTemplateVersion(BaseModel):
    """A version of a SendGrid transactional template."""

    model_config = ConfigDict(frozen=True)

    id: Optional[str] = None
    name: Optional[str] = None
    subject: Optional[str] = None
    active: int = 0
    html_content: Optional[str] = None
    plain_content: Optional[str] = None
    editor: Optional[str] = None
    updated_at: Optional[str] = None


class SendGridTemplate(BaseModel):
    """A SendGrid transactional template."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: Optional[str] = None
    generation: Optional[str] = None
    updated_at: Optional[str] = None
    versions: list[SendGridTemplateVersion] = Field(default_factory=list)


class SendGridBounce(BaseModel):
    """A SendGrid bounced email record."""

    model_config = ConfigDict(frozen=True)

    email: str = ""
    created: Optional[int] = None
    reason: Optional[str] = None
    status: Optional[str] = None


class SendGridSpamReport(BaseModel):
    """A SendGrid spam report record."""

    model_config = ConfigDict(frozen=True)

    email: str = ""
    created: Optional[int] = None
    ip: Optional[str] = None


class SendGridSuppression(BaseModel):
    """A SendGrid global suppression (unsubscribe) record."""

    model_config = ConfigDict(frozen=True)

    email: str = ""
    created: Optional[int] = None
