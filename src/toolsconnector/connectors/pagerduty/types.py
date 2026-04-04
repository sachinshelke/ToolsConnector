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
