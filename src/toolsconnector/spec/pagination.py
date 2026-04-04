"""Pagination specification types."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class PaginationStrategyType(str, Enum):
    """Supported pagination strategies across tool APIs."""

    CURSOR = "cursor"
    TOKEN = "token"
    OFFSET = "offset"
    KEYSET = "keyset"
    PAGE_NUMBER = "page_number"
    LINK_HEADER = "link_header"
    NONE = "none"


class PaginationSpec(BaseModel):
    """Specification for how an action paginates its results.

    Each action that returns a list declares its pagination strategy
    so the runtime can handle multi-page iteration transparently.
    """

    strategy: PaginationStrategyType = PaginationStrategyType.NONE

    # Cursor / Token pagination
    token_param: Optional[str] = Field(
        default=None,
        description="Query parameter name for the page token (e.g., 'pageToken').",
    )
    token_field: Optional[str] = Field(
        default=None,
        description="Response field containing the next page token (e.g., 'nextPageToken').",
    )
    items_field: Optional[str] = Field(
        default=None,
        description="Response field containing the list of items (e.g., 'messages').",
    )

    # Offset pagination
    offset_param: Optional[str] = Field(
        default=None,
        description="Query parameter name for offset (e.g., 'offset').",
    )
    limit_param: Optional[str] = Field(
        default=None,
        description="Query parameter name for limit (e.g., 'limit').",
    )
    total_field: Optional[str] = Field(
        default=None,
        description="Response field with total count (e.g., 'total').",
    )

    # Page number pagination
    page_param: Optional[str] = Field(
        default=None,
        description="Query parameter name for page number (e.g., 'page').",
    )
    per_page_param: Optional[str] = Field(
        default=None,
        description="Query parameter for items per page (e.g., 'per_page').",
    )
    total_pages_field: Optional[str] = Field(
        default=None,
        description="Response field with total page count.",
    )

    # Keyset pagination
    order_field: Optional[str] = Field(
        default=None,
        description="Field used for keyset ordering (e.g., 'id', 'created_at').",
    )
    direction: Optional[str] = Field(
        default="asc",
        description="Sort direction for keyset pagination.",
    )

    # Common
    max_page_size: Optional[int] = Field(
        default=None,
        description="Maximum items per page supported by the API.",
    )
    default_page_size: Optional[int] = Field(
        default=None,
        description="Default items per page if not specified.",
    )

    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific pagination configuration.",
    )
