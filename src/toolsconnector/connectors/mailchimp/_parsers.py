"""Mailchimp API response parsers.

Helper functions to parse raw JSON dicts from the Mailchimp Marketing API
into typed Pydantic models.
"""

from __future__ import annotations

from typing import Any, Optional

from .types import (
    MailchimpCampaign,
    MailchimpCampaignRecipients,
    MailchimpCampaignSettings,
    MailchimpList,
    MailchimpMember,
    MailchimpStats,
)


def _parse_stats(data: Optional[dict[str, Any]]) -> Optional[MailchimpStats]:
    """Parse audience list statistics.

    Args:
        data: Raw stats dict or None.

    Returns:
        MailchimpStats instance or None.
    """
    if not data:
        return None
    return MailchimpStats(
        member_count=data.get("member_count", 0),
        unsubscribe_count=data.get("unsubscribe_count", 0),
        cleaned_count=data.get("cleaned_count", 0),
        open_rate=data.get("open_rate", 0.0),
        click_rate=data.get("click_rate", 0.0),
        campaign_count=data.get("campaign_count", 0),
    )


def _parse_campaign_settings(
    data: Optional[dict[str, Any]],
) -> Optional[MailchimpCampaignSettings]:
    """Parse campaign settings.

    Args:
        data: Raw settings dict or None.

    Returns:
        MailchimpCampaignSettings instance or None.
    """
    if not data:
        return None
    return MailchimpCampaignSettings(
        subject_line=data.get("subject_line"),
        preview_text=data.get("preview_text"),
        title=data.get("title"),
        from_name=data.get("from_name"),
        reply_to=data.get("reply_to"),
    )


def _parse_campaign_recipients(
    data: Optional[dict[str, Any]],
) -> Optional[MailchimpCampaignRecipients]:
    """Parse campaign recipient info.

    Args:
        data: Raw recipients dict or None.

    Returns:
        MailchimpCampaignRecipients instance or None.
    """
    if not data:
        return None
    return MailchimpCampaignRecipients(
        list_id=data.get("list_id"),
        list_name=data.get("list_name"),
        recipient_count=data.get("recipient_count", 0),
    )


def parse_list(data: dict[str, Any]) -> MailchimpList:
    """Parse a MailchimpList from API JSON.

    Args:
        data: Raw JSON dict from the Mailchimp API.

    Returns:
        A MailchimpList instance.
    """
    stats = data.get("stats") or {}
    return MailchimpList(
        id=data["id"],
        name=data.get("name"),
        permission_reminder=data.get("permission_reminder"),
        date_created=data.get("date_created"),
        list_rating=data.get("list_rating"),
        subscribe_url_short=data.get("subscribe_url_short"),
        subscribe_url_long=data.get("subscribe_url_long"),
        visibility=data.get("visibility"),
        member_count=stats.get("member_count", 0),
        unsubscribe_count=stats.get("unsubscribe_count", 0),
        stats=_parse_stats(data.get("stats")),
        web_id=data.get("web_id"),
    )


def parse_member(data: dict[str, Any]) -> MailchimpMember:
    """Parse a MailchimpMember from API JSON.

    Args:
        data: Raw JSON dict from the Mailchimp API.

    Returns:
        A MailchimpMember instance.
    """
    return MailchimpMember(
        id=data["id"],
        email_address=data.get("email_address"),
        unique_email_id=data.get("unique_email_id"),
        full_name=data.get("full_name"),
        status=data.get("status"),
        merge_fields=data.get("merge_fields") or {},
        language=data.get("language"),
        vip=data.get("vip", False),
        email_client=data.get("email_client"),
        list_id=data.get("list_id"),
        tags_count=data.get("tags_count", 0),
        tags=data.get("tags") or [],
        timestamp_signup=data.get("timestamp_signup"),
        timestamp_opt=data.get("timestamp_opt"),
        last_changed=data.get("last_changed"),
        web_id=data.get("web_id"),
    )


def parse_campaign(data: dict[str, Any]) -> MailchimpCampaign:
    """Parse a MailchimpCampaign from API JSON.

    Args:
        data: Raw JSON dict from the Mailchimp API.

    Returns:
        A MailchimpCampaign instance.
    """
    return MailchimpCampaign(
        id=data["id"],
        type=data.get("type"),
        status=data.get("status"),
        emails_sent=data.get("emails_sent", 0),
        send_time=data.get("send_time"),
        create_time=data.get("create_time"),
        content_type=data.get("content_type"),
        archive_url=data.get("archive_url"),
        long_archive_url=data.get("long_archive_url"),
        web_id=data.get("web_id"),
        settings=_parse_campaign_settings(data.get("settings")),
        recipients=_parse_campaign_recipients(data.get("recipients")),
    )
