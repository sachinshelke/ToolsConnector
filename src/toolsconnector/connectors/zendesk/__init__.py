"""Zendesk connector -- tickets, users, comments, and search."""

from __future__ import annotations

from .connector import Zendesk
from .types import (
    ZendeskComment,
    ZendeskGroup,
    ZendeskOrganization,
    ZendeskSearchResult,
    ZendeskTicket,
    ZendeskUser,
)

__all__ = [
    "Zendesk",
    "ZendeskComment",
    "ZendeskGroup",
    "ZendeskOrganization",
    "ZendeskSearchResult",
    "ZendeskTicket",
    "ZendeskUser",
]
