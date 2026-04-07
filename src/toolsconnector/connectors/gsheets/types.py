"""Pydantic models for Google Sheets connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class Sheet(BaseModel):
    """A single sheet (tab) within a spreadsheet."""

    model_config = ConfigDict(frozen=True)

    id: int
    title: str
    index: int = 0
    row_count: int = 0
    column_count: int = 0


class Spreadsheet(BaseModel):
    """A Google Sheets spreadsheet."""

    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    url: Optional[str] = None
    sheets: list[Sheet] = Field(default_factory=list)


class SheetValues(BaseModel):
    """Values returned from a range in a spreadsheet."""

    model_config = ConfigDict(frozen=True)

    range: str = ""
    major_dimension: str = "ROWS"
    values: list[list[Any]] = Field(default_factory=list)


class UpdateResult(BaseModel):
    """Result of updating values in a spreadsheet."""

    model_config = ConfigDict(frozen=True)

    updated_range: str = ""
    updated_rows: int = 0
    updated_columns: int = 0
    updated_cells: int = 0


class AppendResult(BaseModel):
    """Result of appending values to a spreadsheet."""

    model_config = ConfigDict(frozen=True)

    updates: Optional[UpdateResult] = None


class ClearResult(BaseModel):
    """Result of clearing values from a spreadsheet range."""

    model_config = ConfigDict(frozen=True)

    cleared_range: str = ""


class BatchUpdateResult(BaseModel):
    """Result of a batch value update across multiple ranges."""

    model_config = ConfigDict(frozen=True)

    responses: list[UpdateResult] = Field(default_factory=list)
