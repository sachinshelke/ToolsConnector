"""Pydantic models for Mixpanel connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class MixpanelEvent(BaseModel):
    """A tracked Mixpanel event."""

    model_config = ConfigDict(frozen=True)

    event: str = ""
    properties: dict[str, Any] = Field(default_factory=dict)


class MixpanelEventCount(BaseModel):
    """Event name with count for top events."""

    model_config = ConfigDict(frozen=True)

    event: str = ""
    count: int = 0


class MixpanelTrackResult(BaseModel):
    """Result of tracking an event."""

    model_config = ConfigDict(frozen=True)

    status: int = 1
    error: Optional[str] = None


class FunnelStep(BaseModel):
    """A single step in a funnel analysis."""

    model_config = ConfigDict(frozen=True)

    count: int = 0
    step_conv_ratio: float = 0.0
    overall_conv_ratio: float = 0.0
    avg_time: Optional[float] = None
    event: str = ""


class MixpanelFunnel(BaseModel):
    """Funnel analysis result."""

    model_config = ConfigDict(frozen=True)

    funnel_id: int = 0
    name: str = ""
    steps: list[FunnelStep] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class RetentionCohort(BaseModel):
    """A single cohort in retention analysis."""

    model_config = ConfigDict(frozen=True)

    date: str = ""
    count: int = 0
    percentages: list[float] = Field(default_factory=list)


class MixpanelRetention(BaseModel):
    """Retention analysis result."""

    model_config = ConfigDict(frozen=True)

    cohorts: list[RetentionCohort] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class MixpanelProfile(BaseModel):
    """A Mixpanel user profile."""

    model_config = ConfigDict(frozen=True)

    distinct_id: str = ""
    properties: dict[str, Any] = Field(default_factory=dict)
    last_seen: Optional[str] = None


class MixpanelEventName(BaseModel):
    """An event name from the event names list."""

    model_config = ConfigDict(frozen=True)

    name: str = ""
