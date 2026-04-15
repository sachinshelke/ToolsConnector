"""Pydantic models for AWS ALB connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ALBLoadBalancer(BaseModel):
    """An Application Load Balancer."""

    model_config = ConfigDict(frozen=True)

    load_balancer_arn: str = ""
    dns_name: str = ""
    name: str = ""
    scheme: str = ""
    state: str = ""
    type: str = ""
    vpc_id: str = ""
    availability_zones: list[dict[str, Any]] = Field(default_factory=list)
    security_groups: list[str] = Field(default_factory=list)
    created_time: Optional[str] = None


class ALBTargetGroup(BaseModel):
    """An ALB target group."""

    model_config = ConfigDict(frozen=True)

    target_group_arn: str = ""
    target_group_name: str = ""
    protocol: str = ""
    port: int = 0
    vpc_id: str = ""
    health_check_protocol: str = ""
    health_check_path: str = ""
    health_check_interval_seconds: int = 30
    healthy_threshold_count: int = 5
    unhealthy_threshold_count: int = 2
    target_type: str = ""


class ALBListener(BaseModel):
    """An ALB listener."""

    model_config = ConfigDict(frozen=True)

    listener_arn: str = ""
    load_balancer_arn: str = ""
    port: int = 0
    protocol: str = ""
    ssl_policy: str = ""
    certificates: list[dict[str, Any]] = Field(default_factory=list)
    default_actions: list[dict[str, Any]] = Field(default_factory=list)


class ALBRule(BaseModel):
    """An ALB routing rule."""

    model_config = ConfigDict(frozen=True)

    rule_arn: str = ""
    priority: str = ""
    conditions: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    is_default: bool = False


class ALBTargetHealth(BaseModel):
    """Health status of a target in a target group."""

    model_config = ConfigDict(frozen=True)

    target_id: str = ""
    target_port: int = 0
    health_status: str = ""
    health_description: str = ""
