"""Shared state types used across the ToolsConnector type system."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PageState(BaseModel):
    """Tracks pagination state across pages.

    Supports cursor-based, offset-based, and page-number-based pagination
    strategies. Connectors populate whichever fields match their API's
    pagination model and ignore the rest.

    Attributes:
        cursor: Opaque cursor token for cursor-based pagination.
        offset: Numeric offset for offset-based pagination.
        page_number: Current page number for page-number-based pagination.
        total_count: Total number of items available on the server, if known.
        has_more: Whether additional pages exist beyond the current one.
        extra: Arbitrary connector-specific pagination metadata.
    """

    cursor: str | None = None
    offset: int | None = None
    page_number: int | None = None
    total_count: int | None = None
    has_more: bool = False
    extra: dict[str, Any] = Field(default_factory=dict)
