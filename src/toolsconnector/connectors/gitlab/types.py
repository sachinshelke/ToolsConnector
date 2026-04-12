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


class GitLabComment(BaseModel):
    """A comment (note) on a GitLab issue or merge request."""

    model_config = ConfigDict(frozen=True)

    id: int
    body: str = ""
    author: Optional[GitLabUser] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    system: bool = False
    noteable_id: Optional[int] = None
    noteable_type: Optional[str] = None
    noteable_iid: Optional[int] = None


class GitLabJob(BaseModel):
    """A CI/CD job within a GitLab pipeline."""

    model_config = ConfigDict(frozen=True)

    id: int
    name: str = ""
    status: str = "created"
    stage: str = ""
    ref: Optional[str] = None
    tag: bool = False
    coverage: Optional[float] = None
    allow_failure: bool = False
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration: Optional[float] = None
    queued_duration: Optional[float] = None
    web_url: Optional[str] = None
    pipeline_id: Optional[int] = None
    user: Optional[GitLabUser] = None
    runner_name: Optional[str] = None
    failure_reason: Optional[str] = None


class GitLabBranch(BaseModel):
    """A branch in a GitLab project repository."""

    model_config = ConfigDict(frozen=True)

    name: str
    merged: bool = False
    protected: bool = False
    default: bool = False
    developers_can_push: bool = False
    developers_can_merge: bool = False
    can_push: bool = False
    web_url: Optional[str] = None
    commit_id: Optional[str] = None
    commit_message: Optional[str] = None


class GitLabTag(BaseModel):
    """A tag in a GitLab project repository."""

    model_config = ConfigDict(frozen=True)

    name: str
    message: Optional[str] = None
    target: Optional[str] = None
    protected: bool = False
    release_description: Optional[str] = None
    commit_id: Optional[str] = None
    commit_message: Optional[str] = None


class GitLabMember(BaseModel):
    """A member of a GitLab project or group."""

    model_config = ConfigDict(frozen=True)

    id: int
    username: str
    name: Optional[str] = None
    state: str = "active"
    avatar_url: Optional[str] = None
    web_url: Optional[str] = None
    access_level: int = 0
    expires_at: Optional[str] = None
    created_at: Optional[str] = None

    @property
    def access_level_label(self) -> str:
        """Human-readable access level."""
        mapping = {
            10: "Guest",
            20: "Reporter",
            30: "Developer",
            40: "Maintainer",
            50: "Owner",
        }
        return mapping.get(self.access_level, f"Unknown({self.access_level})")
