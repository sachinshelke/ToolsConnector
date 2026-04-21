"""Pydantic models for AWS Route 53 connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class R53HostedZone(BaseModel):
    """A Route 53 hosted zone."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    name: str = ""
    caller_reference: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    resource_record_set_count: int = 0


class R53RecordSet(BaseModel):
    """A DNS resource record set within a hosted zone."""

    model_config = ConfigDict(frozen=True)

    name: str = ""
    type: str = ""
    ttl: Optional[int] = None
    resource_records: list[str] = Field(default_factory=list)
    alias_target: Optional[dict[str, Any]] = None


class R53HealthCheck(BaseModel):
    """A Route 53 health check."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    caller_reference: str = ""
    health_check_config: dict[str, Any] = Field(default_factory=dict)
    health_check_version: int = 0


class R53ChangeInfo(BaseModel):
    """Information about a Route 53 change request."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    status: str = ""
    submitted_at: Optional[str] = None
