"""Pydantic models for Vercel connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class VercelDeployment(BaseModel):
    """A Vercel deployment."""

    model_config = ConfigDict(frozen=True)

    uid: Optional[str] = None
    name: Optional[str] = None
    url: Optional[str] = None
    state: Optional[str] = None
    type: Optional[str] = None
    created: Optional[int] = None
    ready: Optional[int] = None
    creator: Optional[dict[str, Any]] = None
    meta: Optional[dict[str, Any]] = None
    target: Optional[str] = None
    alias_assigned: Optional[bool] = None
    alias_error: Optional[dict[str, Any]] = None
    inspectorUrl: Optional[str] = None
    building_at: Optional[int] = None
    source: Optional[str] = None


class VercelProject(BaseModel):
    """A Vercel project."""

    model_config = ConfigDict(frozen=True)

    id: Optional[str] = None
    name: Optional[str] = None
    framework: Optional[str] = None
    node_version: Optional[str] = None
    build_command: Optional[str] = None
    dev_command: Optional[str] = None
    install_command: Optional[str] = None
    output_directory: Optional[str] = None
    root_directory: Optional[str] = None
    created_at: Optional[int] = None
    updated_at: Optional[int] = None
    latest_deployments: list[dict[str, Any]] = Field(default_factory=list)
    live: Optional[bool] = None
    link: Optional[dict[str, Any]] = None
    env: list[dict[str, Any]] = Field(default_factory=list)


class VercelDomain(BaseModel):
    """A Vercel domain."""

    model_config = ConfigDict(frozen=True)

    name: Optional[str] = None
    apexName: Optional[str] = None
    redirect: Optional[str] = None
    redirect_status_code: Optional[int] = None
    git_branch: Optional[str] = None
    updated_at: Optional[int] = None
    created_at: Optional[int] = None
    verified: Optional[bool] = None
    project_id: Optional[str] = None


class VercelEnvVar(BaseModel):
    """A Vercel environment variable."""

    model_config = ConfigDict(frozen=True)

    id: Optional[str] = None
    key: Optional[str] = None
    value: Optional[str] = None
    type: Optional[str] = None
    target: list[str] = Field(default_factory=list)
    git_branch: Optional[str] = None
    created_at: Optional[int] = None
    updated_at: Optional[int] = None
    system: Optional[bool] = None
    configuration_id: Optional[str] = None


class VercelAlias(BaseModel):
    """A Vercel deployment alias."""

    model_config = ConfigDict(frozen=True)

    uid: Optional[str] = None
    alias: Optional[str] = None
    deployment_id: Optional[str] = None
    project_id: Optional[str] = None
    created_at: Optional[int] = None
