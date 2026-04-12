"""Pydantic models for PagerDuty connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class PDUser(BaseModel):
    """A PagerDuty user."""

    model_config = ConfigDict(frozen=True)

    id: Optional[str] = None
    type: str = "user"
    name: Optional[str] = None
    email: Optional[str] = None
    html_url: Optional[str] = None
    summary: Optional[str] = None
    time_zone: Optional[str] = None
    role: Optional[str] = None
    avatar_url: Optional[str] = None


class PDService(BaseModel):
    """A PagerDuty service."""

    model_config = ConfigDict(frozen=True)

    id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    html_url: Optional[str] = None
    summary: Optional[str] = None
    type: str = "service"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    escalation_policy: Optional[dict[str, Any]] = None
    teams: list[dict[str, Any]] = Field(default_factory=list)
    alert_creation: Optional[str] = None


class PDIncident(BaseModel):
    """A PagerDuty incident."""

    model_config = ConfigDict(frozen=True)

    id: Optional[str] = None
    type: str = "incident"
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    urgency: Optional[str] = None
    html_url: Optional[str] = None
    summary: Optional[str] = None
    incident_number: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_status_change_at: Optional[str] = None
    service: Optional[PDService] = None
    assignments: list[dict[str, Any]] = Field(default_factory=list)
    assigned_via: Optional[str] = None
    escalation_policy: Optional[dict[str, Any]] = None
    teams: list[dict[str, Any]] = Field(default_factory=list)
    acknowledgements: list[dict[str, Any]] = Field(default_factory=list)
    alert_counts: Optional[dict[str, int]] = None


class PDOncall(BaseModel):
    """A PagerDuty on-call entry."""

    model_config = ConfigDict(frozen=True)

    user: Optional[PDUser] = None
    schedule: Optional[dict[str, Any]] = None
    escalation_policy: Optional[dict[str, Any]] = None
    escalation_level: Optional[int] = None
    start: Optional[str] = None
    end: Optional[str] = None


class PDEscalationPolicy(BaseModel):
    """A PagerDuty escalation policy."""

    model_config = ConfigDict(frozen=True)

    id: Optional[str] = None
    type: str = "escalation_policy"
    name: Optional[str] = None
    description: Optional[str] = None
    html_url: Optional[str] = None
    summary: Optional[str] = None
    num_loops: int = 0
    on_call_handoff_notifications: Optional[str] = None
    escalation_rules: list[dict[str, Any]] = Field(default_factory=list)
    services: list[dict[str, Any]] = Field(default_factory=list)
    teams: list[dict[str, Any]] = Field(default_factory=list)


class PDSchedule(BaseModel):
    """A PagerDuty schedule."""

    model_config = ConfigDict(frozen=True)

    id: Optional[str] = None
    type: str = "schedule"
    name: Optional[str] = None
    description: Optional[str] = None
    html_url: Optional[str] = None
    summary: Optional[str] = None
    time_zone: Optional[str] = None
    escalation_policies: list[dict[str, Any]] = Field(default_factory=list)
    users: list[dict[str, Any]] = Field(default_factory=list)


class PDMaintenanceWindow(BaseModel):
    """A PagerDuty maintenance window."""

    model_config = ConfigDict(frozen=True)

    id: Optional[str] = None
    type: str = "maintenance_window"
    summary: Optional[str] = None
    description: Optional[str] = None
    html_url: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    created_by: Optional[dict[str, Any]] = None
    services: list[dict[str, Any]] = Field(default_factory=list)
    teams: list[dict[str, Any]] = Field(default_factory=list)


class PDTeam(BaseModel):
    """A PagerDuty team."""

    model_config = ConfigDict(frozen=True)

    id: Optional[str] = None
    type: str = "team"
    name: Optional[str] = None
    description: Optional[str] = None
    html_url: Optional[str] = None
    summary: Optional[str] = None
    default_role: Optional[str] = None
    parent: Optional[dict[str, Any]] = None


class PDPriority(BaseModel):
    """A PagerDuty incident priority level."""

    model_config = ConfigDict(frozen=True)

    id: Optional[str] = None
    type: str = "priority"
    name: Optional[str] = None
    description: Optional[str] = None
    order: Optional[int] = None
    color: Optional[str] = None
    schema_version: Optional[int] = None
