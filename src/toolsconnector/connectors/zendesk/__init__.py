"""Zendesk connector -- tickets, users, comments, and search."""

from __future__ import annotations

from .connector import Zendesk
from .types import (
    ZendeskComment,
    ZendeskSearchResult,
    ZendeskTicket,
    ZendeskUser,
)

__all__ = [
    "Zendesk",
    "ZendeskComment",
    "ZendeskSearchResult",
    "ZendeskTicket",
    "ZendeskUser",
]
