"""Pydantic models for Segment connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class SegmentTrackResult(BaseModel):
    """Result of a tracking API call (track, identify, page, group, alias)."""

    model_config = ConfigDict(frozen=True)

    success: bool = True
    message: Optional[str] = None


class SegmentEvent(BaseModel):
    """A Segment tracking event."""

    model_config = ConfigDict(frozen=True)

    user_id: str = ""
    event: str = ""
    properties: dict[str, Any] = Field(default_factory=dict)
    timestamp: Optional[str] = None
    context: Optional[dict[str, Any]] = None


class SegmentIdentity(BaseModel):
    """A Segment identify call result."""

    model_config = ConfigDict(frozen=True)

    user_id: str = ""
    traits: dict[str, Any] = Field(default_factory=dict)


class SegmentSourceConnection(BaseModel):
    """Connection metadata for a source."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    name: str = ""
    enabled: bool = True


class SegmentSource(BaseModel):
    """A Segment source (data collection endpoint)."""

    model_config = ConfigDict(frozen=True)

    id: str
    slug: str = ""
    name: str = ""
    workspace_id: str = ""
    enabled: bool = True
    write_keys: list[str] = Field(default_factory=list)
    metadata: Optional[dict[str, Any]] = None
    settings: Optional[dict[str, Any]] = None
    labels: list[dict[str, Any]] = Field(default_factory=list)


class SegmentDestination(BaseModel):
    """A Segment destination (data forwarding endpoint)."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str = ""
    enabled: bool = True
    source_id: str = ""
    connection_mode: str = ""
    metadata: Optional[dict[str, Any]] = None
    settings: Optional[dict[str, Any]] = None
