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


class HubSpotCompany(BaseModel):
    """A HubSpot CRM company."""

    model_config = ConfigDict(frozen=True)

    id: str
    properties: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    archived: bool = False

    @property
    def name(self) -> Optional[str]:
        """Shortcut to the company name property."""
        return self.properties.get("name")

    @property
    def domain(self) -> Optional[str]:
        """Shortcut to the domain property."""
        return self.properties.get("domain")

    @property
    def industry(self) -> Optional[str]:
        """Shortcut to the industry property."""
        return self.properties.get("industry")


class HubSpotTicket(BaseModel):
    """A HubSpot CRM ticket."""

    model_config = ConfigDict(frozen=True)

    id: str
    properties: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    archived: bool = False

    @property
    def subject(self) -> Optional[str]:
        """Shortcut to the subject property."""
        return self.properties.get("subject")

    @property
    def hs_pipeline(self) -> Optional[str]:
        """Shortcut to the pipeline property."""
        return self.properties.get("hs_pipeline")

    @property
    def hs_pipeline_stage(self) -> Optional[str]:
        """Shortcut to the pipeline stage property."""
        return self.properties.get("hs_pipeline_stage")

    @property
    def hs_ticket_priority(self) -> Optional[str]:
        """Shortcut to the priority property."""
        return self.properties.get("hs_ticket_priority")


class HubSpotPipeline(BaseModel):
    """A HubSpot CRM pipeline definition."""

    model_config = ConfigDict(frozen=True)

    id: str
    label: str = ""
    display_order: int = 0
    archived: bool = False
    stages: list[dict[str, Any]] = Field(default_factory=list)
