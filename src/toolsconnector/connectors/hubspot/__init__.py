"""HubSpot connector -- manage contacts, deals, and CRM data."""

from __future__ import annotations

from .connector import HubSpot
from .types import HubSpotContact, HubSpotDeal, HubSpotProperty

__all__ = [
    "HubSpot",
    "HubSpotContact",
    "HubSpotDeal",
    "HubSpotProperty",
]
