"""Pydantic models for AWS CloudFront connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class CFOrigin(BaseModel):
    """A CloudFront distribution origin."""

    model_config = ConfigDict(frozen=True)

    id: str
    domain_name: str
    origin_path: str = ""
    s3_origin_config: Optional[dict[str, Any]] = None
    custom_origin_config: Optional[dict[str, Any]] = None


class CFDistributionSummary(BaseModel):
    """Summary of a CloudFront distribution from ListDistributions."""

    model_config = ConfigDict(frozen=True)

    id: str
    arn: str = ""
    domain_name: str = ""
    status: str = ""
    enabled: bool = False
    comment: str = ""


class CFDistribution(BaseModel):
    """Full CloudFront distribution details."""

    model_config = ConfigDict(frozen=True)

    id: str
    arn: str = ""
    domain_name: str = ""
    status: str = ""
    enabled: bool = False
    comment: str = ""
    last_modified: Optional[str] = None
    origins: list[dict[str, Any]] = Field(default_factory=list)
    default_cache_behavior: dict[str, Any] = Field(default_factory=dict)


class CFDistributionConfig(BaseModel):
    """CloudFront distribution configuration for create/update."""

    model_config = ConfigDict(frozen=True)

    caller_reference: str = ""
    comment: str = ""
    enabled: bool = True
    default_root_object: str = ""
    origins: list[dict[str, Any]] = Field(default_factory=list)
    default_cache_behavior: dict[str, Any] = Field(default_factory=dict)
    aliases: dict[str, Any] = Field(default_factory=dict)
    viewer_certificate: dict[str, Any] = Field(default_factory=dict)


class CFInvalidation(BaseModel):
    """A CloudFront cache invalidation."""

    model_config = ConfigDict(frozen=True)

    id: str
    status: str = ""
    create_time: Optional[str] = None
    invalidation_batch: dict[str, Any] = Field(default_factory=dict)
