"""LinkedIn Lead Sync connector — retrieve consented leads from Lead Gen Forms."""

from __future__ import annotations

from .connector import LinkedInLeads
from .types import LeadAnswer, LeadForm, LeadFormQuestion, LeadResponse

__all__ = [
    "LinkedInLeads",
    "LeadForm",
    "LeadFormQuestion",
    "LeadResponse",
    "LeadAnswer",
]
