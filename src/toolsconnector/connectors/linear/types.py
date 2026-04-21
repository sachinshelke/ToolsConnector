"""Pydantic models for Linear connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Embedded / shared models
# ---------------------------------------------------------------------------


class LinearUser(BaseModel):
    """A Linear user reference."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: Optional[str] = None
    display_name: Optional[str] = None
    email: Optional[str] = None
    avatar_url: Optional[str] = None
    active: bool = True


class LinearState(BaseModel):
    """A workflow state in Linear."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str = ""
    type: str = ""
    color: Optional[str] = None
    position: Optional[float] = None


class LinearLabel(BaseModel):
    """An issue label in Linear."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str = ""
    color: Optional[str] = None


# ---------------------------------------------------------------------------
# Top-level response models
# ---------------------------------------------------------------------------


class LinearIssue(BaseModel):
    """A Linear issue."""

    model_config = ConfigDict(frozen=True)

    id: str
    identifier: str = ""
    title: str = ""
    description: Optional[str] = None
    priority: int = 0
    priority_label: str = ""
    state: Optional[LinearState] = None
    assignee: Optional[LinearUser] = None
    creator: Optional[LinearUser] = None
    team_id: Optional[str] = None
    project_id: Optional[str] = None
    url: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    completed_at: Optional[str] = None
    canceled_at: Optional[str] = None
    due_date: Optional[str] = None
    estimate: Optional[float] = None
    labels: list[LinearLabel] = Field(default_factory=list)


class LinearTeam(BaseModel):
    """A Linear team."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str = ""
    key: str = ""
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    private: bool = False


class LinearProject(BaseModel):
    """A Linear project."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str = ""
    description: Optional[str] = None
    slug_id: Optional[str] = None
    state: str = ""
    url: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    started_at: Optional[str] = None
    target_date: Optional[str] = None
    progress: float = 0.0
    lead: Optional[LinearUser] = None


class LinearCycle(BaseModel):
    """A cycle (sprint) in Linear."""

    model_config = ConfigDict(frozen=True)

    id: str
    number: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None
    completed_at: Optional[str] = None
    progress: float = 0.0
    scope_count: Optional[int] = None
    completed_scope_count: Optional[int] = None
    team_id: Optional[str] = None


class LinearComment(BaseModel):
    """A comment on a Linear issue."""

    model_config = ConfigDict(frozen=True)

    id: str
    body: str = ""
    user: Optional[LinearUser] = None
    issue_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    url: Optional[str] = None
