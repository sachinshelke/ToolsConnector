"""Pydantic models for AWS ECR connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ECRRepository(BaseModel):
    """An ECR repository."""

    model_config = ConfigDict(frozen=True)

    repository_name: str = ""
    repository_arn: str = ""
    registry_id: str = ""
    repository_uri: str = ""
    created_at: Optional[str] = None
    image_scanning_configuration: dict[str, Any] = Field(default_factory=dict)
    image_tag_mutability: str = "MUTABLE"


class ECRImage(BaseModel):
    """An image in an ECR repository."""

    model_config = ConfigDict(frozen=True)

    image_digest: str = ""
    image_tags: list[str] = Field(default_factory=list)
    image_pushed_at: Optional[str] = None
    image_size_in_bytes: Optional[int] = None
    image_manifest_media_type: Optional[str] = None


class ECRAuthorizationData(BaseModel):
    """Authorization data for Docker login to ECR."""

    model_config = ConfigDict(frozen=True)

    authorization_token: str = ""
    expires_at: Optional[str] = None
    proxy_endpoint: str = ""


class ECRLifecyclePolicy(BaseModel):
    """A lifecycle policy for an ECR repository."""

    model_config = ConfigDict(frozen=True)

    registry_id: str = ""
    repository_name: str = ""
    lifecycle_policy_text: str = ""


class ECRBatchDeleteResult(BaseModel):
    """Result of a batch image deletion."""

    model_config = ConfigDict(frozen=True)

    image_ids: list[dict[str, Any]] = Field(default_factory=list)
    failures: list[dict[str, Any]] = Field(default_factory=list)
