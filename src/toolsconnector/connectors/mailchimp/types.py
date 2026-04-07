"""Pydantic models for Mailchimp connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Embedded / shared models
# ---------------------------------------------------------------------------


class MailchimpStats(BaseModel):
    """Statistics for a Mailchimp audience list."""

    model_config = ConfigDict(frozen=True)

    member_count: int = 0
    unsubscribe_count: int = 0
    cleaned_count: int = 0
    open_rate: float = 0.0
    click_rate: float = 0.0
    campaign_count: int = 0


class MailchimpCampaignSettings(BaseModel):
    """Settings for a Mailchimp campaign."""

    model_config = ConfigDict(frozen=True)

    subject_line: Optional[str] = None
    preview_text: Optional[str] = None
    title: Optional[str] = None
    from_name: Optional[str] = None
    reply_to: Optional[str] = None


class MailchimpCampaignRecipients(BaseModel):
    """Recipient information for a Mailchimp campaign."""

    model_config = ConfigDict(frozen=True)

    list_id: Optional[str] = None
    list_name: Optional[str] = None
    recipient_count: int = 0


# ---------------------------------------------------------------------------
# Top-level response models
# ---------------------------------------------------------------------------


class MailchimpList(BaseModel):
    """A Mailchimp audience list."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: Optional[str] = None
    permission_reminder: Optional[str] = None
    date_created: Optional[str] = None
    list_rating: Optional[int] = None
    subscribe_url_short: Optional[str] = None
    subscribe_url_long: Optional[str] = None
    visibility: Optional[str] = None
    member_count: int = 0
    unsubscribe_count: int = 0
    stats: Optional[MailchimpStats] = None
    web_id: Optional[int] = None


class MailchimpMember(BaseModel):
    """A member (subscriber) in a Mailchimp audience list."""

    model_config = ConfigDict(frozen=True)

    id: str
    email_address: Optional[str] = None
    unique_email_id: Optional[str] = None
    full_name: Optional[str] = None
    status: Optional[str] = None
    merge_fields: dict[str, Any] = Field(default_factory=dict)
    language: Optional[str] = None
    vip: bool = False
    email_client: Optional[str] = None
    list_id: Optional[str] = None
    tags_count: int = 0
    tags: list[dict[str, Any]] = Field(default_factory=list)
    timestamp_signup: Optional[str] = None
    timestamp_opt: Optional[str] = None
    last_changed: Optional[str] = None
    web_id: Optional[int] = None


class MailchimpCampaign(BaseModel):
    """A Mailchimp email campaign."""

    model_config = ConfigDict(frozen=True)

    id: str
    type: Optional[str] = None
    status: Optional[str] = None
    emails_sent: int = 0
    send_time: Optional[str] = None
    create_time: Optional[str] = None
    content_type: Optional[str] = None
    archive_url: Optional[str] = None
    long_archive_url: Optional[str] = None
    web_id: Optional[int] = None
    settings: Optional[MailchimpCampaignSettings] = None
    recipients: Optional[MailchimpCampaignRecipients] = None


class MailchimpSegment(BaseModel):
    """A Mailchimp list segment (saved audience segment)."""

    model_config = ConfigDict(frozen=True)

    id: int
    name: str = ""
    member_count: int = 0
    type: Optional[str] = None
    list_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class MailchimpCampaignReport(BaseModel):
    """A Mailchimp campaign report with performance metrics."""

    model_config = ConfigDict(frozen=True)

    id: str
    campaign_title: Optional[str] = None
    emails_sent: int = 0
    opens: int = 0
    unique_opens: int = 0
    clicks: int = 0
    subscriber_clicks: int = 0
    unsubscribed: int = 0
    bounces: Optional[dict[str, Any]] = None
    send_time: Optional[str] = None
