"""Pydantic models for Google Tasks connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class TaskList(BaseModel):
    """A Google Tasks task list."""

    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    updated: Optional[str] = None


class GoogleTask(BaseModel):
    """A single task in Google Tasks."""

    model_config = ConfigDict(frozen=True)

    id: str
    title: str = ""
    notes: Optional[str] = None
    status: str = "needsAction"
    due: Optional[str] = None
    completed: Optional[str] = None
    parent: Optional[str] = None
    position: Optional[str] = None
    links: list[dict[str, Any]] = Field(default_factory=list)
