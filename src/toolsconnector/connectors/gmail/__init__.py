"""Gmail connector — read, send, and manage emails."""

from __future__ import annotations

from .connector import Gmail
from .types import Attachment, DraftId, Email, EmailAddress, Label, MessageId

__all__ = [
    "Gmail",
    "Email",
    "EmailAddress",
    "Label",
    "MessageId",
    "DraftId",
    "Attachment",
]
