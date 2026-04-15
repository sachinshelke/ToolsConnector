"""AWS EC2 connector -- launch and manage virtual server instances."""

from __future__ import annotations

from .connector import EC2
from .types import (
    EC2Address,
    EC2Image,
    EC2Instance,
    EC2InstanceType,
    EC2KeyPair,
    EC2SecurityGroup,
    EC2Subnet,
    EC2Volume,
    EC2Vpc,
)

__all__ = [
    "EC2",
    "EC2Address",
    "EC2Image",
    "EC2Instance",
    "EC2InstanceType",
    "EC2KeyPair",
    "EC2SecurityGroup",
    "EC2Subnet",
    "EC2Volume",
    "EC2Vpc",
]
