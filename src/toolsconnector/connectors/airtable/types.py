"""Pydantic models for Airtable connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class AirtableField(BaseModel):
    """Metadata about a single field (column) in an Airtable table."""

    model_config = ConfigDict(frozen=True)

    id: Optional[str] = None
    name: str = ""
    type: Optional[str] = None
    description: Optional[str] = None


class AirtableTable(BaseModel):
    """Metadata about a table within an Airtable base."""

    model_config = ConfigDict(frozen=True)

    id: Optional[str] = None
    name: str = ""
    description: Optional[str] = None
    fields: list[AirtableField] = Field(default_factory=list)


class AirtableBase(BaseModel):
    """Metadata about an Airtable base."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    name: str = ""
    permission_level: Optional[str] = None


class AirtableRecord(BaseModel):
    """A single Airtable record.

    The ``fields`` dict maps column names to their values.  Airtable
    field values can be strings, numbers, arrays, or nested objects
    depending on the field type.
    """

    model_config = ConfigDict(frozen=True)

    id: str = ""
    created_time: Optional[str] = None
    fields: dict[str, Any] = Field(default_factory=dict)


class AirtableWebhook(BaseModel):
    """An Airtable webhook subscription."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    type: Optional[str] = None
    is_hook_enabled: bool = True
    notification_url: Optional[str] = None
    expiration_time: Optional[str] = None
    cursor_for_next_payload: Optional[int] = None
