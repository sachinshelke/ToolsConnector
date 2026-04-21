"""Pydantic models for AWS RDS connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class RDSInstance(BaseModel):
    """An RDS database instance."""

    model_config = ConfigDict(frozen=True)

    db_instance_identifier: str = ""
    db_instance_class: str = ""
    engine: str = ""
    engine_version: str = ""
    db_instance_status: str = ""
    master_username: str = ""
    endpoint_address: str = ""
    endpoint_port: int = 0
    allocated_storage: int = 0
    instance_create_time: Optional[str] = None
    availability_zone: str = ""
    multi_az: bool = False
    publicly_accessible: bool = False
    storage_type: str = ""
    db_instance_arn: str = ""
    vpc_security_groups: list[dict[str, Any]] = Field(default_factory=list)
    db_subnet_group_name: str = ""
    tags: dict[str, str] = Field(default_factory=dict)


class RDSSnapshot(BaseModel):
    """An RDS database snapshot."""

    model_config = ConfigDict(frozen=True)

    db_snapshot_identifier: str = ""
    db_instance_identifier: str = ""
    snapshot_create_time: Optional[str] = None
    engine: str = ""
    allocated_storage: int = 0
    status: str = ""
    availability_zone: str = ""
    snapshot_type: str = ""
    encrypted: bool = False
    db_snapshot_arn: str = ""


class RDSCluster(BaseModel):
    """An Aurora database cluster."""

    model_config = ConfigDict(frozen=True)

    db_cluster_identifier: str = ""
    db_cluster_arn: str = ""
    status: str = ""
    engine: str = ""
    engine_version: str = ""
    endpoint: str = ""
    reader_endpoint: str = ""
    port: int = 0
    master_username: str = ""
    database_name: str = ""
    multi_az: bool = False
    db_cluster_members: list[dict[str, Any]] = Field(default_factory=list)


class RDSSubnetGroup(BaseModel):
    """A DB subnet group."""

    model_config = ConfigDict(frozen=True)

    db_subnet_group_name: str = ""
    db_subnet_group_description: str = ""
    vpc_id: str = ""
    subnet_group_status: str = ""
    subnets: list[dict[str, Any]] = Field(default_factory=list)


class RDSEvent(BaseModel):
    """An RDS event."""

    model_config = ConfigDict(frozen=True)

    source_identifier: str = ""
    source_type: str = ""
    message: str = ""
    date: Optional[str] = None
    source_arn: str = ""
