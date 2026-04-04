"""Pydantic models for Asana connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Embedded / shared models
# ---------------------------------------------------------------------------


class AsanaUser(BaseModel):
    """An Asana user reference."""

    model_config = ConfigDict(frozen=True)

    gid: str
    name: Optional[str] = None
    email: Optional[str] = None
    resource_type: str = "user"


# ---------------------------------------------------------------------------
# Top-level response models
# ---------------------------------------------------------------------------


class AsanaWorkspace(BaseModel):
    """An Asana workspace."""

    model_config = ConfigDict(frozen=True)

    gid: str
    name: str = ""
    resource_type: str = "workspace"
    is_organization: Optional[bool] = None


class AsanaProject(BaseModel):
    """An Asana project."""

    model_config = ConfigDict(frozen=True)

    gid: str
    name: str = ""
    resource_type: str = "project"
    archived: Optional[bool] = None
    color: Optional[str] = None
    created_at: Optional[str] = None
    modified_at: Optional[str] = None
    notes: Optional[str] = None
    owner: Optional[AsanaUser] = None
    workspace: Optional[AsanaWorkspace] = None
    current_status: Optional[dict[str, Any]] = None
    due_on: Optional[str] = None
    start_on: Optional[str] = None
    public: Optional[bool] = None


class AsanaTask(BaseModel):
    """An Asana task."""

    model_config = ConfigDict(frozen=True)

    gid: str
    name: str = ""
    resource_type: str = "task"
    assignee: Optional[AsanaUser] = None
    completed: bool = False
    completed_at: Optional[str] = None
    created_at: Optional[str] = None
    modified_at: Optional[str] = None
    due_on: Optional[str] = None
    due_at: Optional[str] = None
    notes: Optional[str] = None
    html_notes: Optional[str] = None
    start_on: Optional[str] = None
    tags: list[dict[str, Any]] = Field(default_factory=list)
    projects: list[dict[str, Any]] = Field(default_factory=list)
    parent: Optional[dict[str, Any]] = None
    permalink_url: Optional[str] = None
    num_subtasks: Optional[int] = None


class AsanaComment(BaseModel):
    """A story (comment) on an Asana task."""

    model_config = ConfigDict(frozen=True)

    gid: str
    resource_type: str = "story"
    text: str = ""
    html_text: Optional[str] = None
    created_at: Optional[str] = None
    created_by: Optional[AsanaUser] = None
    type: Optional[str] = None
