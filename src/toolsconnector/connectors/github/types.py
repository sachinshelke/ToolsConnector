"""Pydantic models for GitHub connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Shared / embedded models
# ---------------------------------------------------------------------------


class GitHubUser(BaseModel):
    """A GitHub user or organisation account."""

    model_config = ConfigDict(frozen=True)

    login: str
    id: int
    avatar_url: Optional[str] = None
    html_url: Optional[str] = None
    type: str = "User"
    site_admin: bool = False


class GitHubLabel(BaseModel):
    """A label attached to an issue or pull request."""

    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    color: str = ""
    description: Optional[str] = None


class GitHubMilestone(BaseModel):
    """A milestone on a repository."""

    model_config = ConfigDict(frozen=True)

    id: int
    number: int
    title: str
    state: str = "open"
    description: Optional[str] = None


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class Repository(BaseModel):
    """A GitHub repository."""

    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    full_name: str
    owner: Optional[GitHubUser] = None
    private: bool = False
    html_url: Optional[str] = None
    description: Optional[str] = None
    fork: bool = False
    language: Optional[str] = None
    default_branch: str = "main"
    stargazers_count: int = 0
    watchers_count: int = 0
    forks_count: int = 0
    open_issues_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    pushed_at: Optional[str] = None
    archived: bool = False
    disabled: bool = False
    topics: list[str] = Field(default_factory=list)
    visibility: str = "public"


class Issue(BaseModel):
    """A GitHub issue."""

    model_config = ConfigDict(frozen=True)

    id: int
    number: int
    title: str
    body: Optional[str] = None
    state: str = "open"
    html_url: Optional[str] = None
    user: Optional[GitHubUser] = None
    labels: list[GitHubLabel] = Field(default_factory=list)
    assignees: list[GitHubUser] = Field(default_factory=list)
    milestone: Optional[GitHubMilestone] = None
    comments: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    closed_at: Optional[str] = None
    locked: bool = False


class Comment(BaseModel):
    """A comment on an issue or pull request."""

    model_config = ConfigDict(frozen=True)

    id: int
    body: str
    user: Optional[GitHubUser] = None
    html_url: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class PullRequest(BaseModel):
    """A GitHub pull request."""

    model_config = ConfigDict(frozen=True)

    id: int
    number: int
    title: str
    body: Optional[str] = None
    state: str = "open"
    html_url: Optional[str] = None
    user: Optional[GitHubUser] = None
    labels: list[GitHubLabel] = Field(default_factory=list)
    assignees: list[GitHubUser] = Field(default_factory=list)
    milestone: Optional[GitHubMilestone] = None
    head_ref: Optional[str] = None
    base_ref: Optional[str] = None
    draft: bool = False
    merged: bool = False
    mergeable: Optional[bool] = None
    merged_at: Optional[str] = None
    merged_by: Optional[GitHubUser] = None
    comments: int = 0
    review_comments: int = 0
    commits: int = 0
    additions: int = 0
    deletions: int = 0
    changed_files: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    closed_at: Optional[str] = None

    @classmethod
    def from_api(cls, data: dict) -> PullRequest:
        """Create a PullRequest from the GitHub API response.

        Args:
            data: Raw JSON dict from the GitHub API.

        Returns:
            A PullRequest instance.
        """
        return cls(
            id=data["id"],
            number=data["number"],
            title=data["title"],
            body=data.get("body"),
            state=data.get("state", "open"),
            html_url=data.get("html_url"),
            user=GitHubUser(**data["user"]) if data.get("user") else None,
            labels=[GitHubLabel(**lb) for lb in data.get("labels", [])],
            assignees=[GitHubUser(**a) for a in data.get("assignees", [])],
            milestone=(
                GitHubMilestone(**data["milestone"])
                if data.get("milestone")
                else None
            ),
            head_ref=data.get("head", {}).get("ref") if data.get("head") else None,
            base_ref=data.get("base", {}).get("ref") if data.get("base") else None,
            draft=data.get("draft", False),
            merged=data.get("merged", False),
            mergeable=data.get("mergeable"),
            merged_at=data.get("merged_at"),
            merged_by=(
                GitHubUser(**data["merged_by"])
                if data.get("merged_by")
                else None
            ),
            comments=data.get("comments", 0),
            review_comments=data.get("review_comments", 0),
            commits=data.get("commits", 0),
            additions=data.get("additions", 0),
            deletions=data.get("deletions", 0),
            changed_files=data.get("changed_files", 0),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            closed_at=data.get("closed_at"),
        )


class CommitAuthor(BaseModel):
    """Git commit author details."""

    model_config = ConfigDict(frozen=True)

    name: Optional[str] = None
    email: Optional[str] = None
    date: Optional[str] = None


class CommitDetail(BaseModel):
    """The inner commit object (git metadata)."""

    model_config = ConfigDict(frozen=True)

    message: str
    author: Optional[CommitAuthor] = None
    committer: Optional[CommitAuthor] = None


class Commit(BaseModel):
    """A GitHub commit."""

    model_config = ConfigDict(frozen=True)

    sha: str
    commit: Optional[CommitDetail] = None
    author: Optional[GitHubUser] = None
    committer: Optional[GitHubUser] = None
    html_url: Optional[str] = None


class CodeSearchResult(BaseModel):
    """A single code search result."""

    model_config = ConfigDict(frozen=True)

    name: str
    path: str
    sha: str
    html_url: Optional[str] = None
    repository: Optional[Repository] = None
    score: float = 0.0
    text_matches: list[dict] = Field(default_factory=list)
