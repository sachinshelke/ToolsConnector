"""Gmail connector — read, send, and manage emails."""

from __future__ import annotations

from .connector import Gmail
from .types import Attachment, DraftId, Email, EmailAddress, Label, LabelColor, MessageId, Thread

__all__ = [
    "Gmail",
    "Attachment",
    "DraftId",
    "Email",
    "EmailAddress",
    "Label",
    "LabelColor",
    "MessageId",
    "Thread",
]
