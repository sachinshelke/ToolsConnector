"""Pydantic models for AWS ECS connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ECSCluster(BaseModel):
    """An ECS cluster."""

    model_config = ConfigDict(frozen=True)

    cluster_arn: str = ""
    cluster_name: str = ""
    status: str = ""
    registered_container_instances_count: int = 0
    running_tasks_count: int = 0
    pending_tasks_count: int = 0
    active_services_count: int = 0
    settings: list[dict[str, Any]] = Field(default_factory=list)


class ECSService(BaseModel):
    """An ECS service."""

    model_config = ConfigDict(frozen=True)

    service_arn: str = ""
    service_name: str = ""
    cluster_arn: str = ""
    status: str = ""
    desired_count: int = 0
    running_count: int = 0
    pending_count: int = 0
    launch_type: str = ""
    task_definition: str = ""
    load_balancers: list[dict[str, Any]] = Field(default_factory=list)
    deployment_configuration: dict[str, Any] = Field(default_factory=dict)
    deployments: list[dict[str, Any]] = Field(default_factory=list)
    created_at: Optional[str] = None
    events: list[dict[str, Any]] = Field(default_factory=list)


class ECSTaskDefinition(BaseModel):
    """An ECS task definition."""

    model_config = ConfigDict(frozen=True)

    task_definition_arn: str = ""
    family: str = ""
    revision: int = 0
    status: str = ""
    container_definitions: list[dict[str, Any]] = Field(default_factory=list)
    cpu: str = ""
    memory: str = ""
    network_mode: str = ""
    requires_compatibilities: list[str] = Field(default_factory=list)
    execution_role_arn: str = ""
    task_role_arn: str = ""
    volumes: list[dict[str, Any]] = Field(default_factory=list)


class ECSTask(BaseModel):
    """A running or stopped ECS task."""

    model_config = ConfigDict(frozen=True)

    task_arn: str = ""
    task_definition_arn: str = ""
    cluster_arn: str = ""
    container_instance_arn: str = ""
    last_status: str = ""
    desired_status: str = ""
    cpu: str = ""
    memory: str = ""
    containers: list[dict[str, Any]] = Field(default_factory=list)
    started_at: Optional[str] = None
    stopped_at: Optional[str] = None
    stopped_reason: str = ""
    launch_type: str = ""
    connectivity: str = ""


class ECSDeployment(BaseModel):
    """An ECS service deployment."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    status: str = ""
    task_definition: str = ""
    desired_count: int = 0
    running_count: int = 0
    pending_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    launch_type: str = ""
