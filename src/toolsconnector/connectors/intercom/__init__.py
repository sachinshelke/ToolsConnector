"""Intercom connector -- manage contacts, conversations, and messaging."""

from __future__ import annotations

from .connector import Intercom
from .types import (
    IntercomAdmin,
    IntercomContact,
    IntercomConversation,
    IntercomMessage,
)

__all__ = [
    "Intercom",
    "IntercomAdmin",
    "IntercomContact",
    "IntercomConversation",
    "IntercomMessage",
]
