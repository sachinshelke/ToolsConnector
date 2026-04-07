"""Google Sheets connector -- manage spreadsheets and cell data."""

from __future__ import annotations

from .connector import GoogleSheets
from .types import (
    AppendResult,
    BatchUpdateResult,
    ClearResult,
    Sheet,
    SheetValues,
    Spreadsheet,
    UpdateResult,
)

__all__ = [
    "GoogleSheets",
    "AppendResult",
    "BatchUpdateResult",
    "ClearResult",
    "Sheet",
    "SheetValues",
    "Spreadsheet",
    "UpdateResult",
]
