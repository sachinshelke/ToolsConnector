"""Outlook connector -- read, send, and manage emails via Microsoft Graph."""

from __future__ import annotations

from .connector import Outlook
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
    OutlookMessageId,
)

__all__ = [
    "Outlook",
    "EmailRecipient",
    "MailFolder",
    "MailRule",
    "MailTip",
    "OutlookAttachment",
    "OutlookCalendarEvent",
    "OutlookCategory",
    "OutlookContact",
    "OutlookMessage",
    "OutlookMessageId",
]
