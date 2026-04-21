"""Pydantic models for Google Docs connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class Document(BaseModel):
    """A Google Docs document."""

    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    body_text: Optional[str] = None
    revision_id: Optional[str] = None


class BatchUpdateResponse(BaseModel):
    """Response from a batch update on a document."""

    model_config = ConfigDict(frozen=True)

    document_id: str = ""
    replies: list[dict[str, Any]] = Field(default_factory=list)
