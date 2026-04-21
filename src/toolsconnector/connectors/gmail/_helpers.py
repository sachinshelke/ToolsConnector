"""Gmail API response helpers.

Helper functions to parse raw JSON dicts from the Gmail API
into typed Pydantic models.
"""

from __future__ import annotations

import base64
from typing import Any, Optional

from .types import (
    Draft,
    Email,
    EmailAddress,
    HistoryRecord,
    Label,
    Thread,
    VacationSettings,
)


def parse_email_address(raw: str) -> EmailAddress:
    """Parse a 'Display Name <email>' string into an EmailAddress.

    Args:
        raw: Raw address string from a Gmail header value.

    Returns:
        Parsed EmailAddress with name and email fields.
    """
    raw = raw.strip()
    if "<" in raw and raw.endswith(">"):
        name_part = raw[: raw.index("<")].strip().strip('"')
        email_part = raw[raw.index("<") + 1 : -1].strip()
        return EmailAddress(email=email_part, name=name_part or None)
    return EmailAddress(email=raw)


def get_header(headers: list[dict[str, str]], name: str) -> str:
    """Extract a header value by name from the Gmail headers array.

    Args:
        headers: List of {"name": ..., "value": ...} dicts from the API.
        name: Case-insensitive header name to find.

    Returns:
        The header value, or empty string if not found.
    """
    lower_name = name.lower()
    for h in headers:
        if h.get("name", "").lower() == lower_name:
            return h.get("value", "")
    return ""


def extract_body(payload: dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """Recursively extract plain-text and HTML body from message payload.

    Args:
        payload: The Gmail API message payload dict.

    Returns:
        Tuple of (plain_text_body, html_body), either may be None.
    """
    text_body: Optional[str] = None
    html_body: Optional[str] = None

    mime_type = payload.get("mimeType", "")

    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            text_body = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    elif mime_type == "text/html":
        data = payload.get("body", {}).get("data", "")
        if data:
            html_body = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    elif mime_type.startswith("multipart/"):
        for part in payload.get("parts", []):
            t, h = extract_body(part)
            if t and not text_body:
                text_body = t
            if h and not html_body:
                html_body = h

    return text_body, html_body


def has_attachments(payload: dict[str, Any]) -> bool:
    """Check whether the message payload contains file attachments.

    Args:
        payload: The Gmail API message payload dict.

    Returns:
        True if at least one part has a non-empty filename.
    """
    for part in payload.get("parts", []):
        if part.get("filename"):
            return True
        if part.get("parts"):
            if has_attachments(part):
                return True
    return False


def parse_message(data: dict[str, Any]) -> Email:
    """Parse a Gmail API message response into an Email model.

    Args:
        data: Raw JSON response from GET /users/me/messages/{id}.

    Returns:
        Populated Email instance.
    """
    payload = data.get("payload", {})
    headers = payload.get("headers", [])

    subject = get_header(headers, "Subject")
    from_raw = get_header(headers, "From")
    to_raw = get_header(headers, "To")
    cc_raw = get_header(headers, "Cc")
    date_str = get_header(headers, "Date")

    from_addr = parse_email_address(from_raw) if from_raw else None
    to_addrs = [parse_email_address(a) for a in to_raw.split(",") if a.strip()] if to_raw else []
    cc_addrs = [parse_email_address(a) for a in cc_raw.split(",") if a.strip()] if cc_raw else []

    text_body, html_body = extract_body(payload)

    return Email(
        id=data.get("id", ""),
        thread_id=data.get("threadId", ""),
        subject=subject,
        from_address=from_addr,
        to=to_addrs,
        cc=cc_addrs,
        date=date_str,
        snippet=data.get("snippet", ""),
        body_text=text_body,
        body_html=html_body,
        labels=data.get("labelIds", []),
        has_attachments=has_attachments(payload),
    )


def parse_thread(data: dict[str, Any]) -> Thread:
    """Parse a Gmail API thread response into a Thread model.

    Args:
        data: Raw JSON response from a threads endpoint.

    Returns:
        Populated Thread instance.
    """
    return Thread(
        id=data.get("id", ""),
        snippet=data.get("snippet", ""),
        history_id=data.get("historyId"),
        messages_count=len(data.get("messages", [])),
    )


def parse_label(data: dict[str, Any]) -> Label:
    """Parse a Gmail API label response into a Label model.

    Args:
        data: Raw JSON response from a labels endpoint.

    Returns:
        Populated Label instance.
    """
    return Label(
        id=data.get("id", ""),
        name=data.get("name", ""),
        type=data.get("type", "user"),
        messages_total=data.get("messagesTotal", 0),
        messages_unread=data.get("messagesUnread", 0),
    )


def parse_draft(data: dict[str, Any]) -> Draft:
    """Parse a Gmail API draft response into a Draft model.

    Args:
        data: Raw JSON response from a drafts endpoint.

    Returns:
        Populated Draft instance with parsed message if present.
    """
    msg_data = data.get("message", {})
    message = parse_message(msg_data) if msg_data.get("id") else None
    return Draft(
        id=data.get("id", ""),
        message=message,
    )


def parse_history_record(data: dict[str, Any]) -> HistoryRecord:
    """Parse a Gmail API history entry into a HistoryRecord model.

    Args:
        data: A single entry from the history list response.

    Returns:
        Populated HistoryRecord instance.
    """
    messages_added = [m.get("message", {}).get("id", "") for m in data.get("messagesAdded", [])]
    messages_deleted = [m.get("message", {}).get("id", "") for m in data.get("messagesDeleted", [])]
    labels_added = [m.get("message", {}).get("id", "") for m in data.get("labelsAdded", [])]
    labels_removed = [m.get("message", {}).get("id", "") for m in data.get("labelsRemoved", [])]
    return HistoryRecord(
        id=str(data.get("id", "")),
        messages_added=messages_added,
        messages_deleted=messages_deleted,
        labels_added=labels_added,
        labels_removed=labels_removed,
    )


def parse_vacation_settings(data: dict[str, Any]) -> VacationSettings:
    """Parse a Gmail API vacation settings response.

    Args:
        data: Raw JSON response from the vacation settings endpoint.

    Returns:
        Populated VacationSettings instance.
    """
    return VacationSettings(
        enable_auto_reply=data.get("enableAutoReply", False),
        response_subject=data.get("responseSubject"),
        response_body_plain_text=data.get("responseBodyPlainText"),
        response_body_html=data.get("responseBodyHtml"),
        start_time=str(data["startTime"]) if data.get("startTime") else None,
        end_time=str(data["endTime"]) if data.get("endTime") else None,
    )
