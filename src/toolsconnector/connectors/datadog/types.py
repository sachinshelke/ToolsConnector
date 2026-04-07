"""Pydantic models for Datadog connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class DatadogMonitor(BaseModel):
    """A Datadog monitor definition."""

    model_config = ConfigDict(frozen=True)

    id: Optional[int] = None
    name: Optional[str] = None
    type: Optional[str] = None
    query: Optional[str] = None
    message: Optional[str] = None
    overall_state: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    created: Optional[str] = None
    modified: Optional[str] = None
    creator: Optional[dict[str, Any]] = None
    options: Optional[dict[str, Any]] = None
    multi: bool = False
    priority: Optional[int] = None


class DatadogEvent(BaseModel):
    """A Datadog event."""

    model_config = ConfigDict(frozen=True)

    id: Optional[int] = None
    title: Optional[str] = None
    text: Optional[str] = None
    date_happened: Optional[int] = None
    priority: Optional[str] = None
    host: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    alert_type: Optional[str] = None
    source_type_name: Optional[str] = None
    url: Optional[str] = None


class DatadogMetricPoint(BaseModel):
    """A single metric data point."""

    model_config = ConfigDict(frozen=True)

    timestamp: Optional[float] = None
    value: Optional[float] = None


class DatadogMetric(BaseModel):
    """A Datadog metric series result."""

    model_config = ConfigDict(frozen=True)

    metric: Optional[str] = None
    display_name: Optional[str] = None
    unit: Optional[str] = None
    scope: Optional[str] = None
    expression: Optional[str] = None
    pointlist: list[DatadogMetricPoint] = Field(default_factory=list)
    start: Optional[float] = None
    end: Optional[float] = None
    interval: Optional[int] = None


class DatadogDashboard(BaseModel):
    """A Datadog dashboard summary."""

    model_config = ConfigDict(frozen=True)

    id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    layout_type: Optional[str] = None
    author_handle: Optional[str] = None
    created_at: Optional[str] = None
    modified_at: Optional[str] = None
    is_read_only: bool = False


class DatadogHost(BaseModel):
    """A Datadog host."""

    model_config = ConfigDict(frozen=True)

    name: Optional[str] = None
    id: Optional[int] = None
    aliases: list[str] = Field(default_factory=list)
    apps: list[str] = Field(default_factory=list)
    is_muted: bool = False
    last_reported_time: Optional[int] = None
    up: Optional[bool] = None


class DatadogDowntime(BaseModel):
    """A Datadog scheduled downtime."""

    model_config = ConfigDict(frozen=True)

    id: Optional[int] = None
    scope: Optional[list[str]] = None
    start: Optional[int] = None
    end: Optional[int] = None
    message: Optional[str] = None
    active: bool = True
