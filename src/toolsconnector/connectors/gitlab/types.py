"""Pydantic models for GitLab connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Shared / embedded models
# ---------------------------------------------------------------------------


class GitLabUser(BaseModel):
    """A GitLab user account."""

    model_config = ConfigDict(frozen=True)

    id: int
    username: str
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    web_url: Optional[str] = None
    state: str = "active"


class GitLabNamespace(BaseModel):
    """A GitLab namespace (user or group)."""

    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    path: str
    kind: str = "user"
    full_path: Optional[str] = None
    web_url: Optional[str] = None


class GitLabLabel(BaseModel):
    """A label on a GitLab issue or merge request."""

    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    color: str = ""
    description: Optional[str] = None


class GitLabMilestone(BaseModel):
    """A milestone on a GitLab project."""

    model_config = ConfigDict(frozen=True)

    id: int
    iid: int
    title: str
    state: str = "active"
    description: Optional[str] = None
    due_date: Optional[str] = None


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class Project(BaseModel):
    """A GitLab project (repository)."""

    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    name_with_namespace: Optional[str] = None
    path: str
    path_with_namespace: Optional[str] = None
    description: Optional[str] = None
    visibility: str = "private"
    web_url: Optional[str] = None
    ssh_url_to_repo: Optional[str] = None
    http_url_to_repo: Optional[str] = None
    namespace: Optional[GitLabNamespace] = None
    owner: Optional[GitLabUser] = None
    default_branch: str = "main"
    star_count: int = 0
    forks_count: int = 0
    open_issues_count: int = 0
    archived: bool = False
    created_at: Optional[str] = None
    last_activity_at: Optional[str] = None
    topics: list[str] = Field(default_factory=list)
    empty_repo: bool = False


class GitLabIssue(BaseModel):
    """A GitLab issue."""

    model_config = ConfigDict(frozen=True)

    id: int
    iid: int
    title: str
    description: Optional[str] = None
    state: str = "opened"
    web_url: Optional[str] = None
    author: Optional[GitLabUser] = None
    assignees: list[GitLabUser] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    milestone: Optional[GitLabMilestone] = None
    upvotes: int = 0
    downvotes: int = 0
    user_notes_count: int = 0
    confidential: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    closed_at: Optional[str] = None
    due_date: Optional[str] = None


class MergeRequest(BaseModel):
    """A GitLab merge request."""

    model_config = ConfigDict(frozen=True)

    id: int
    iid: int
    title: str
    description: Optional[str] = None
    state: str = "opened"
    web_url: Optional[str] = None
    author: Optional[GitLabUser] = None
    assignees: list[GitLabUser] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    milestone: Optional[GitLabMilestone] = None
    source_branch: Optional[str] = None
    target_branch: Optional[str] = None
    draft: bool = False
    merge_status: Optional[str] = None
    merged_by: Optional[GitLabUser] = None
    merged_at: Optional[str] = None
    user_notes_count: int = 0
    upvotes: int = 0
    downvotes: int = 0
    has_conflicts: bool = False
    changes_count: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    closed_at: Optional[str] = None


class PipelineRef(BaseModel):
    """Reference details for a pipeline."""

    model_config = ConfigDict(frozen=True)

    ref: Optional[str] = None
    sha: Optional[str] = None


class Pipeline(BaseModel):
    """A GitLab CI/CD pipeline."""

    model_config = ConfigDict(frozen=True)

    id: int
    iid: Optional[int] = None
    project_id: Optional[int] = None
    status: str = "created"
    source: Optional[str] = None
    ref: Optional[str] = None
    sha: Optional[str] = None
    web_url: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration: Optional[int] = None
    queued_duration: Optional[float] = None
    coverage: Optional[str] = None
    user: Optional[GitLabUser] = None
