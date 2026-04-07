"""Response parsers for the HubSpot connector."""

from __future__ import annotations

from typing import Any, Optional

from .types import (
    HubSpotCompany,
    HubSpotContact,
    HubSpotDeal,
    HubSpotPipeline,
    HubSpotTicket,
)


def parse_contact(data: dict[str, Any]) -> HubSpotContact:
    """Parse a raw HubSpot contact JSON into a HubSpotContact model."""
    return HubSpotContact(
        id=data.get("id", ""),
        properties=data.get("properties", {}),
        created_at=data.get("createdAt"),
        updated_at=data.get("updatedAt"),
        archived=data.get("archived", False),
    )


def parse_deal(data: dict[str, Any]) -> HubSpotDeal:
    """Parse a raw HubSpot deal JSON into a HubSpotDeal model."""
    return HubSpotDeal(
        id=data.get("id", ""),
        properties=data.get("properties", {}),
        created_at=data.get("createdAt"),
        updated_at=data.get("updatedAt"),
        archived=data.get("archived", False),
    )


def parse_company(data: dict[str, Any]) -> HubSpotCompany:
    """Parse a raw HubSpot company JSON into a HubSpotCompany model."""
    return HubSpotCompany(
        id=data.get("id", ""),
        properties=data.get("properties", {}),
        created_at=data.get("createdAt"),
        updated_at=data.get("updatedAt"),
        archived=data.get("archived", False),
    )


def parse_ticket(data: dict[str, Any]) -> HubSpotTicket:
    """Parse a raw HubSpot ticket JSON into a HubSpotTicket model."""
    return HubSpotTicket(
        id=data.get("id", ""),
        properties=data.get("properties", {}),
        created_at=data.get("createdAt"),
        updated_at=data.get("updatedAt"),
        archived=data.get("archived", False),
    )


def parse_pipeline(data: dict[str, Any]) -> HubSpotPipeline:
    """Parse a raw HubSpot pipeline JSON into a HubSpotPipeline model."""
    return HubSpotPipeline(
        id=data.get("id", ""),
        label=data.get("label", ""),
        display_order=data.get("displayOrder", 0),
        archived=data.get("archived", False),
        stages=data.get("stages", []),
    )


def extract_cursor(data: dict[str, Any]) -> Optional[str]:
    """Extract the next cursor from the HubSpot paging envelope.

    Args:
        data: Raw API response dict.

    Returns:
        The ``after`` cursor string, or ``None`` if no more pages.
    """
    paging = data.get("paging")
    if not paging:
        return None
    next_page = paging.get("next")
    if not next_page:
        return None
    return next_page.get("after")
