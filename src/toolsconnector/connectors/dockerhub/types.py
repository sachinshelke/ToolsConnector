"""Pydantic models for Docker Hub connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class DockerRepo(BaseModel):
    """A Docker Hub repository."""

    model_config = ConfigDict(frozen=True)

    name: Optional[str] = None
    namespace: Optional[str] = None
    repository_type: Optional[str] = None
    status: int = 0
    status_description: Optional[str] = None
    description: Optional[str] = None
    is_private: bool = False
    star_count: int = 0
    pull_count: int = 0
    last_updated: Optional[str] = None
    date_registered: Optional[str] = None
    affiliation: Optional[str] = None
    media_types: list[str] = Field(default_factory=list)
    content_types: list[str] = Field(default_factory=list)
    full_description: Optional[str] = None


class DockerTag(BaseModel):
    """A Docker Hub repository tag."""

    model_config = ConfigDict(frozen=True)

    id: Optional[int] = None
    name: Optional[str] = None
    full_size: Optional[int] = None
    v2: Optional[bool] = None
    tag_status: Optional[str] = None
    tag_last_pulled: Optional[str] = None
    tag_last_pushed: Optional[str] = None
    last_updated: Optional[str] = None
    digest: Optional[str] = None
    images: list[dict[str, Any]] = Field(default_factory=list)
    creator: Optional[int] = None
    last_updater: Optional[int] = None
    repository: Optional[int] = None


class DockerUser(BaseModel):
    """A Docker Hub user."""

    model_config = ConfigDict(frozen=True)

    id: Optional[str] = None
    username: Optional[str] = None
    full_name: Optional[str] = None
    location: Optional[str] = None
    company: Optional[str] = None
    profile_url: Optional[str] = None
    date_joined: Optional[str] = None
    gravatar_url: Optional[str] = None
    gravatar_email: Optional[str] = None
    type: Optional[str] = None


class DockerOrg(BaseModel):
    """A Docker Hub organization."""

    model_config = ConfigDict(frozen=True)

    id: Optional[str] = None
    orgname: Optional[str] = None
    full_name: Optional[str] = None
    location: Optional[str] = None
    company: Optional[str] = None
    profile_url: Optional[str] = None
    date_joined: Optional[str] = None
    gravatar_url: Optional[str] = None
    gravatar_email: Optional[str] = None
    type: Optional[str] = None
