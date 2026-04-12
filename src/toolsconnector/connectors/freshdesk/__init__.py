"""Freshdesk connector -- manage support tickets and contacts."""

from __future__ import annotations

from .connector import Freshdesk
from .types import (
    FreshdeskCompany,
    FreshdeskContact,
    FreshdeskReply,
    FreshdeskTicket,
    FreshdeskTicketField,
)

__all__ = [
    "Freshdesk",
    "FreshdeskCompany",
    "FreshdeskContact",
    "FreshdeskReply",
    "FreshdeskTicket",
    "FreshdeskTicketField",
]
