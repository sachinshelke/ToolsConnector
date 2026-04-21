"""Internal response parsers for the Outlook connector.

Converts raw MS Graph JSON dicts into typed Pydantic models.
"""

from __future__ import annotations

from typing import Any

from .types import (
    EmailRecipient,
    MailFolder,
    MailRule,
    MailTip,
    OutlookAttachment,
    OutlookCalendarEvent,
    OutlookCategory,
    OutlookContact,
    OutlookMessage,
)


def parse_recipient(raw: dict[str, Any]) -> EmailRecipient:
    """Parse an MS Graph ``emailAddress`` object into an EmailRecipient.

    Args:
        raw: Dict with ``emailAddress`` containing ``name`` and ``address``.

    Returns:
        Parsed EmailRecipient.
    """
    addr = raw.get("emailAddress", {})
    return EmailRecipient(
        email=addr.get("address", ""),
        name=addr.get("name") or None,
    )


def parse_message(data: dict[str, Any]) -> OutlookMessage:
    """Parse an MS Graph message JSON into an OutlookMessage model.

    Args:
        data: Raw JSON response from the messages endpoint.

    Returns:
        Populated OutlookMessage instance.
    """
    from_raw = data.get("from")
    from_addr = parse_recipient(from_raw) if from_raw else None

    to_list = [parse_recipient(r) for r in data.get("toRecipients", [])]
    cc_list = [parse_recipient(r) for r in data.get("ccRecipients", [])]

    body = data.get("body", {})

    return OutlookMessage(
        id=data.get("id", ""),
        subject=data.get("subject"),
        body_preview=data.get("bodyPreview"),
        body_content=body.get("content"),
        body_content_type=body.get("contentType"),
        from_address=from_addr,
        to_recipients=to_list,
        cc_recipients=cc_list,
        received_datetime=data.get("receivedDateTime"),
        sent_datetime=data.get("sentDateTime"),
        is_read=data.get("isRead", False),
        has_attachments=data.get("hasAttachments", False),
        importance=data.get("importance", "normal"),
        conversation_id=data.get("conversationId"),
        web_link=data.get("webLink"),
    )


def parse_contact(data: dict[str, Any]) -> OutlookContact:
    """Parse an MS Graph contact JSON into an OutlookContact model.

    Args:
        data: Raw JSON response from the contacts endpoint.

    Returns:
        Populated OutlookContact instance.
    """
    email_addresses = [
        {"address": e.get("address"), "name": e.get("name")} for e in data.get("emailAddresses", [])
    ]
    phone_numbers = (
        [
            {"number": p.get("number"), "type": p.get("type")}
            for p in (data.get("phones") or data.get("businessPhones", []))
        ]
        if data.get("phones") or data.get("businessPhones")
        else []
    )

    return OutlookContact(
        id=data.get("id", ""),
        given_name=data.get("givenName"),
        surname=data.get("surname"),
        display_name=data.get("displayName"),
        email_addresses=email_addresses,
        phone_numbers=phone_numbers,
        company_name=data.get("companyName"),
        job_title=data.get("jobTitle"),
        created_datetime=data.get("createdDateTime"),
        last_modified_datetime=data.get("lastModifiedDateTime"),
    )


def parse_calendar_event(data: dict[str, Any]) -> OutlookCalendarEvent:
    """Parse an MS Graph calendar event JSON into an OutlookCalendarEvent.

    Args:
        data: Raw JSON response from the events endpoint.

    Returns:
        Populated OutlookCalendarEvent instance.
    """
    start = data.get("start", {})
    end = data.get("end", {})
    location = data.get("location", {})
    organizer = data.get("organizer", {}).get("emailAddress", {})
    body = data.get("body", {})

    attendees = [
        {
            "email": a.get("emailAddress", {}).get("address"),
            "name": a.get("emailAddress", {}).get("name"),
            "status": a.get("status", {}).get("response"),
        }
        for a in data.get("attendees", [])
    ]

    return OutlookCalendarEvent(
        id=data.get("id", ""),
        subject=data.get("subject"),
        body_preview=data.get("bodyPreview"),
        body_content=body.get("content"),
        start_datetime=start.get("dateTime"),
        start_timezone=start.get("timeZone"),
        end_datetime=end.get("dateTime"),
        end_timezone=end.get("timeZone"),
        location=location.get("displayName"),
        is_all_day=data.get("isAllDay", False),
        is_cancelled=data.get("isCancelled", False),
        organizer_name=organizer.get("name"),
        organizer_email=organizer.get("address"),
        attendees=attendees,
        web_link=data.get("webLink"),
        created_datetime=data.get("createdDateTime"),
        last_modified_datetime=data.get("lastModifiedDateTime"),
    )


def parse_folder(data: dict[str, Any]) -> MailFolder:
    """Parse an MS Graph mailFolder JSON into a MailFolder model.

    Args:
        data: Raw JSON response from the mailFolders endpoint.

    Returns:
        Populated MailFolder instance.
    """
    return MailFolder(
        id=data.get("id", ""),
        display_name=data.get("displayName", ""),
        parent_folder_id=data.get("parentFolderId"),
        child_folder_count=data.get("childFolderCount", 0),
        total_item_count=data.get("totalItemCount", 0),
        unread_item_count=data.get("unreadItemCount", 0),
    )


def parse_attachment(data: dict[str, Any]) -> OutlookAttachment:
    """Parse an MS Graph attachment JSON into an OutlookAttachment model.

    Args:
        data: Raw JSON response from the attachments endpoint.

    Returns:
        Populated OutlookAttachment instance.
    """
    return OutlookAttachment(
        id=data.get("id", ""),
        name=data.get("name"),
        content_type=data.get("contentType"),
        size=data.get("size", 0),
        is_inline=data.get("isInline", False),
        last_modified_datetime=data.get("lastModifiedDateTime"),
        content_id=data.get("contentId"),
        content_bytes=data.get("contentBytes"),
    )


def parse_mail_rule(data: dict[str, Any]) -> MailRule:
    """Parse an MS Graph messageRule JSON into a MailRule model.

    Args:
        data: Raw JSON response from the messageRules endpoint.

    Returns:
        Populated MailRule instance.
    """
    return MailRule(
        id=data.get("id", ""),
        display_name=data.get("displayName"),
        sequence=data.get("sequence", 0),
        is_enabled=data.get("isEnabled", True),
        conditions=data.get("conditions"),
        actions=data.get("actions"),
        exceptions=data.get("exceptions"),
        has_error=data.get("hasError", False),
        is_read_only=data.get("isReadOnly", False),
    )


def parse_category(data: dict[str, Any]) -> OutlookCategory:
    """Parse an MS Graph outlookCategory JSON into an OutlookCategory model.

    Args:
        data: Raw JSON response from the masterCategories endpoint.

    Returns:
        Populated OutlookCategory instance.
    """
    return OutlookCategory(
        id=data.get("id", ""),
        display_name=data.get("displayName", ""),
        color=data.get("color"),
    )


def parse_mail_tip(data: dict[str, Any]) -> MailTip:
    """Parse an MS Graph mailTips JSON into a MailTip model.

    Args:
        data: Raw JSON response from the getMailTips endpoint.

    Returns:
        Populated MailTip instance.
    """
    email_addr = data.get("emailAddress", {})
    return MailTip(
        email_address=email_addr.get("address") if isinstance(email_addr, dict) else email_addr,
        automatic_replies=data.get("automaticReplies"),
        mailbox_full=data.get("mailboxFull", False),
        max_message_size=data.get("maxMessageSize"),
        is_moderated=data.get("isModerated", False),
        delivery_restricted=data.get("deliveryRestricted", False),
        external_member_count=data.get("externalMemberCount"),
        total_member_count=data.get("totalMemberCount"),
    )
