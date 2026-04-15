"""Pydantic models for AWS CloudWatch connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


class CWMetric(BaseModel):
    """A CloudWatch metric descriptor."""

    model_config = ConfigDict(frozen=True)

    namespace: str = ""
    metric_name: str = ""
    dimensions: list[dict[str, Any]] = Field(default_factory=list)


class CWMetricDataResult(BaseModel):
    """A single result from a GetMetricData query."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    label: str = ""
    timestamps: list[str] = Field(default_factory=list)
    values: list[float] = Field(default_factory=list)
    status_code: str = ""


# ---------------------------------------------------------------------------
# Alarms
# ---------------------------------------------------------------------------


class CWMetricAlarm(BaseModel):
    """A CloudWatch metric alarm."""

    model_config = ConfigDict(frozen=True)

    alarm_name: str = ""
    alarm_arn: str = ""
    state_value: str = ""
    state_reason: str = ""
    metric_name: str = ""
    namespace: str = ""
    statistic: str = ""
    period: int = 0
    evaluation_periods: int = 0
    threshold: float = 0.0
    comparison_operator: str = ""
    actions_enabled: bool = False
    alarm_actions: list[str] = Field(default_factory=list)
    dimensions: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Dashboards
# ---------------------------------------------------------------------------


class CWDashboard(BaseModel):
    """A CloudWatch dashboard."""

    model_config = ConfigDict(frozen=True)

    dashboard_name: str = ""
    dashboard_arn: str = ""
    last_modified: Optional[str] = None
    size: int = 0


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------


class CWLogGroup(BaseModel):
    """A CloudWatch Logs log group."""

    model_config = ConfigDict(frozen=True)

    log_group_name: str = ""
    log_group_arn: str = ""
    creation_time: Optional[int] = None
    retention_in_days: Optional[int] = None
    stored_bytes: Optional[int] = None


class CWLogStream(BaseModel):
    """A CloudWatch Logs log stream."""

    model_config = ConfigDict(frozen=True)

    log_stream_name: str = ""
    creation_time: Optional[int] = None
    first_event_timestamp: Optional[int] = None
    last_event_timestamp: Optional[int] = None
    last_ingestion_time: Optional[int] = None
    stored_bytes: Optional[int] = None


class CWLogEvent(BaseModel):
    """A single CloudWatch Logs event."""

    model_config = ConfigDict(frozen=True)

    timestamp: Optional[int] = None
    message: str = ""
    ingestion_time: Optional[int] = None
