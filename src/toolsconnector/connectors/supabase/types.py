"""Pydantic models for Supabase connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class SupabaseRecord(BaseModel):
    """A single record returned from a Supabase table.

    The ``data`` field contains the row as a dict of column names to
    values.  The structure depends on the table schema.
    """

    model_config = ConfigDict(frozen=True)

    data: dict[str, Any] = Field(default_factory=dict)


class SupabaseRPCResult(BaseModel):
    """Result of a Supabase RPC (stored procedure) invocation.

    The ``result`` field contains whatever the function returns, which
    may be a scalar, list, or dict depending on the function definition.
    """

    model_config = ConfigDict(frozen=True)

    result: Any = None


class SupabaseTable(BaseModel):
    """Metadata about a Supabase table discovered via the OpenAPI schema."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: Optional[str] = None
    columns: list[str] = Field(default_factory=list)
