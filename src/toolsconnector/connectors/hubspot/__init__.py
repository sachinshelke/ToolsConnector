"""HubSpot connector -- manage contacts, deals, and CRM data."""

from __future__ import annotations

from .connector import HubSpot
from .types import (
    HubSpotCompany,
    HubSpotContact,
    HubSpotDeal,
    HubSpotPipeline,
    HubSpotProperty,
    HubSpotTicket,
)

__all__ = [
    "HubSpot",
    "HubSpotCompany",
    "HubSpotContact",
    "HubSpotDeal",
    "HubSpotPipeline",
    "HubSpotProperty",
    "HubSpotTicket",
]
