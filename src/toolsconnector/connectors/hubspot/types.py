"""Pydantic models for HubSpot connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Embedded / shared models
# ---------------------------------------------------------------------------


class HubSpotProperty(BaseModel):
    """A single HubSpot object property key-value pair."""

    model_config = ConfigDict(frozen=True)

    name: str = ""
    value: Optional[str] = None
    label: Optional[str] = None
    description: Optional[str] = None
    field_type: Optional[str] = None
    type: Optional[str] = None


# ---------------------------------------------------------------------------
# Top-level response models
# ---------------------------------------------------------------------------


class HubSpotContact(BaseModel):
    """A HubSpot CRM contact."""

    model_config = ConfigDict(frozen=True)

    id: str
    properties: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    archived: bool = False

    @property
    def email(self) -> Optional[str]:
        """Shortcut to the email property."""
        return self.properties.get("email")

    @property
    def firstname(self) -> Optional[str]:
        """Shortcut to the firstname property."""
        return self.properties.get("firstname")

    @property
    def lastname(self) -> Optional[str]:
        """Shortcut to the lastname property."""
        return self.properties.get("lastname")


class HubSpotDeal(BaseModel):
    """A HubSpot CRM deal."""

    model_config = ConfigDict(frozen=True)

    id: str
    properties: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    archived: bool = False

    @property
    def dealname(self) -> Optional[str]:
        """Shortcut to the dealname property."""
        return self.properties.get("dealname")

    @property
    def amount(self) -> Optional[str]:
        """Shortcut to the amount property."""
        return self.properties.get("amount")

    @property
    def dealstage(self) -> Optional[str]:
        """Shortcut to the dealstage property."""
        return self.properties.get("dealstage")

    @property
    def pipeline(self) -> Optional[str]:
        """Shortcut to the pipeline property."""
        return self.properties.get("pipeline")
