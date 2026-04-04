"""Freshdesk connector -- manage support tickets and contacts."""

from __future__ import annotations

from .connector import Freshdesk
from .types import FreshdeskContact, FreshdeskReply, FreshdeskTicket

__all__ = [
    "Freshdesk",
    "FreshdeskContact",
    "FreshdeskReply",
    "FreshdeskTicket",
]
