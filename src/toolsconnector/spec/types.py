"""Type specification for custom connector types."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class TypeSpec(BaseModel):
    """Specification for a custom type defined by a connector.

    Connectors define tool-specific types (Email, Label, Product, etc.)
    that are referenced in action input/output schemas. This spec captures
    the JSON Schema representation of those types.
    """

    name: str = Field(description="Type name (e.g., 'Email', 'Label').")
    description: str = Field(default="", description="Human-readable description.")
    json_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON Schema for this type.",
    )
    python_type: Optional[str] = Field(
        default=None,
        description="Fully qualified Python type path (e.g., 'toolsconnector.connectors.gmail.types.Email').",
    )
