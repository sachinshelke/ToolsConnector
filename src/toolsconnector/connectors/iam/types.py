"""Pydantic models for AWS IAM connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class IAMRole(BaseModel):
    """An IAM role."""

    model_config = ConfigDict(frozen=True)

    role_name: str = ""
    role_id: str = ""
    arn: str = ""
    path: str = ""
    create_date: Optional[str] = None
    assume_role_policy_document: str = ""
    description: str = ""
    max_session_duration: int = 3600
    tags: dict[str, str] = Field(default_factory=dict)


class IAMPolicy(BaseModel):
    """An IAM managed policy."""

    model_config = ConfigDict(frozen=True)

    policy_name: str = ""
    policy_id: str = ""
    arn: str = ""
    path: str = ""
    default_version_id: str = ""
    attachment_count: int = 0
    is_attachable: bool = True
    create_date: Optional[str] = None
    update_date: Optional[str] = None
    description: str = ""


class IAMInstanceProfile(BaseModel):
    """An IAM instance profile."""

    model_config = ConfigDict(frozen=True)

    instance_profile_name: str = ""
    instance_profile_id: str = ""
    arn: str = ""
    path: str = ""
    roles: list[str] = Field(default_factory=list)
    create_date: Optional[str] = None


class IAMAccessKey(BaseModel):
    """An IAM access key."""

    model_config = ConfigDict(frozen=True)

    access_key_id: str = ""
    status: str = ""
    create_date: Optional[str] = None
    user_name: str = ""


class IAMUser(BaseModel):
    """An IAM user."""

    model_config = ConfigDict(frozen=True)

    user_name: str = ""
    user_id: str = ""
    arn: str = ""
    path: str = ""
    create_date: Optional[str] = None
    tags: dict[str, str] = Field(default_factory=dict)


class IAMAttachedPolicy(BaseModel):
    """A managed policy attached to an IAM entity."""

    model_config = ConfigDict(frozen=True)

    policy_name: str = ""
    policy_arn: str = ""
