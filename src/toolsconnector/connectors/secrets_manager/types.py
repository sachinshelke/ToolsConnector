"""Pydantic models for AWS Secrets Manager connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class SMSecret(BaseModel):
    """A secret stored in AWS Secrets Manager."""

    model_config = ConfigDict(frozen=True)

    arn: str = ""
    name: str = ""
    description: str = ""
    kms_key_id: str = ""
    rotation_enabled: bool = False
    last_rotated_date: Optional[str] = None
    last_changed_date: Optional[str] = None
    last_accessed_date: Optional[str] = None
    tags: dict[str, str] = Field(default_factory=dict)
    created_date: Optional[str] = None


class SMSecretValue(BaseModel):
    """The value of a secret retrieved from AWS Secrets Manager."""

    model_config = ConfigDict(frozen=True)

    arn: str = ""
    name: str = ""
    version_id: str = ""
    secret_string: str = ""
    secret_binary: Optional[str] = None
    version_stages: list[str] = Field(default_factory=list)
    created_date: Optional[str] = None


class SMSecretVersion(BaseModel):
    """A version of a secret in AWS Secrets Manager."""

    model_config = ConfigDict(frozen=True)

    version_id: str = ""
    version_stages: list[str] = Field(default_factory=list)
    created_date: Optional[str] = None
