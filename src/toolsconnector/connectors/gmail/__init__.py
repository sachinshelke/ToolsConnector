"""Gmail connector — read, send, and manage emails."""

from __future__ import annotations

from .connector import Gmail
from .types import (
    Attachment,
    Draft,
    DraftId,
    Email,
    EmailAddress,
    HistoryRecord,
    Label,
    LabelColor,
    MessageId,
    Thread,
    UserProfile,
    VacationSettings,
)

__all__ = [
    "Gmail",
    "Attachment",
    "Draft",
    "DraftId",
    "Email",
    "EmailAddress",
    "HistoryRecord",
    "Label",
    "LabelColor",
    "MessageId",
    "Thread",
    "UserProfile",
    "VacationSettings",
]
