"""Pydantic models for AWS EC2 connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class EC2Instance(BaseModel):
    """An EC2 virtual server instance."""

    model_config = ConfigDict(frozen=True)

    instance_id: str = ""
    instance_type: str = ""
    state: str = ""
    public_ip: Optional[str] = None
    private_ip: Optional[str] = None
    launch_time: Optional[str] = None
    availability_zone: str = ""
    subnet_id: str = ""
    vpc_id: str = ""
    security_groups: list[dict[str, Any]] = Field(default_factory=list)
    tags: dict[str, str] = Field(default_factory=dict)
    image_id: str = ""
    key_name: str = ""
    platform: str = ""


class EC2KeyPair(BaseModel):
    """An EC2 SSH key pair."""

    model_config = ConfigDict(frozen=True)

    key_name: str = ""
    key_pair_id: str = ""
    key_fingerprint: str = ""
    key_material: Optional[str] = None


class EC2SecurityGroup(BaseModel):
    """A VPC security group."""

    model_config = ConfigDict(frozen=True)

    group_id: str = ""
    group_name: str = ""
    description: str = ""
    vpc_id: str = ""
    ip_permissions: list[dict[str, Any]] = Field(default_factory=list)
    ip_permissions_egress: list[dict[str, Any]] = Field(default_factory=list)
    tags: dict[str, str] = Field(default_factory=dict)


class EC2Address(BaseModel):
    """An Elastic IP address."""

    model_config = ConfigDict(frozen=True)

    allocation_id: str = ""
    public_ip: str = ""
    instance_id: str = ""
    association_id: str = ""
    domain: str = ""
    network_interface_id: str = ""
    tags: dict[str, str] = Field(default_factory=dict)


class EC2Image(BaseModel):
    """An Amazon Machine Image (AMI)."""

    model_config = ConfigDict(frozen=True)

    image_id: str = ""
    name: str = ""
    description: str = ""
    state: str = ""
    architecture: str = ""
    platform_details: str = ""
    owner_id: str = ""
    creation_date: Optional[str] = None
    public: bool = False


class EC2InstanceType(BaseModel):
    """An EC2 instance type specification."""

    model_config = ConfigDict(frozen=True)

    instance_type: str = ""
    vcpu_count: int = 0
    memory_size_mb: int = 0
    current_generation: bool = False


class EC2Vpc(BaseModel):
    """A Virtual Private Cloud."""

    model_config = ConfigDict(frozen=True)

    vpc_id: str = ""
    cidr_block: str = ""
    state: str = ""
    is_default: bool = False
    tags: dict[str, str] = Field(default_factory=dict)


class EC2Subnet(BaseModel):
    """A VPC subnet."""

    model_config = ConfigDict(frozen=True)

    subnet_id: str = ""
    vpc_id: str = ""
    cidr_block: str = ""
    availability_zone: str = ""
    available_ip_count: int = 0
    tags: dict[str, str] = Field(default_factory=dict)


class EC2Volume(BaseModel):
    """An EBS volume."""

    model_config = ConfigDict(frozen=True)

    volume_id: str = ""
    size: int = 0
    state: str = ""
    availability_zone: str = ""
    volume_type: str = ""
    iops: int = 0
    encrypted: bool = False
    tags: dict[str, str] = Field(default_factory=dict)
