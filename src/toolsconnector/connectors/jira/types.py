"""Pydantic models for Jira connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Embedded / shared models
# ---------------------------------------------------------------------------


class JiraUser(BaseModel):
    """A Jira user reference."""

    model_config = ConfigDict(frozen=True)

    account_id: str = ""
    display_name: Optional[str] = None
    email_address: Optional[str] = None
    active: bool = True
    avatar_url: Optional[str] = None


class JiraPriority(BaseModel):
    """Issue priority level."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    name: str = ""
    icon_url: Optional[str] = None


class JiraStatus(BaseModel):
    """Issue status."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    name: str = ""
    category_key: Optional[str] = None


class JiraIssueType(BaseModel):
    """Issue type metadata."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    name: str = ""
    subtask: bool = False
    icon_url: Optional[str] = None


# ---------------------------------------------------------------------------
# Top-level response models
# ---------------------------------------------------------------------------


class JiraIssue(BaseModel):
    """A Jira issue (ticket)."""

    model_config = ConfigDict(frozen=True)

    id: str
    key: str
    self_url: Optional[str] = None
    summary: str = ""
    description: Optional[Any] = None
    status: Optional[JiraStatus] = None
    issue_type: Optional[JiraIssueType] = None
    priority: Optional[JiraPriority] = None
    assignee: Optional[JiraUser] = None
    reporter: Optional[JiraUser] = None
    project_key: str = ""
    created: Optional[str] = None
    updated: Optional[str] = None
    labels: list[str] = Field(default_factory=list)
    components: list[str] = Field(default_factory=list)
    fix_versions: list[str] = Field(default_factory=list)


class JiraProject(BaseModel):
    """A Jira project."""

    model_config = ConfigDict(frozen=True)

    id: str
    key: str
    name: str = ""
    project_type_key: Optional[str] = None
    lead: Optional[JiraUser] = None
    avatar_url: Optional[str] = None
    self_url: Optional[str] = None


class JiraComment(BaseModel):
    """A comment on a Jira issue."""

    model_config = ConfigDict(frozen=True)

    id: str
    body: Any = None
    author: Optional[JiraUser] = None
    created: Optional[str] = None
    updated: Optional[str] = None
    self_url: Optional[str] = None


class JiraTransition(BaseModel):
    """An available status transition for an issue."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str = ""
    to_status: Optional[JiraStatus] = None
    has_screen: bool = False


class JiraSprint(BaseModel):
    """A Jira Agile sprint."""

    model_config = ConfigDict(frozen=True)

    id: int
    name: str = ""
    state: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    complete_date: Optional[str] = None
    board_id: Optional[int] = None
    goal: Optional[str] = None
    self_url: Optional[str] = None


class JiraBoard(BaseModel):
    """A Jira Agile board."""

    model_config = ConfigDict(frozen=True)

    id: int
    name: str = ""
    type: Optional[str] = None
    project_key: Optional[str] = None
    self_url: Optional[str] = None


class JiraAttachment(BaseModel):
    """An attachment on a Jira issue."""

    model_config = ConfigDict(frozen=True)

    id: str
    filename: str = ""
    mime_type: Optional[str] = None
    size: Optional[int] = None
    author: Optional[JiraUser] = None
    created: Optional[str] = None
    content_url: Optional[str] = None
    self_url: Optional[str] = None


class JiraWorklog(BaseModel):
    """A worklog entry on a Jira issue."""

    model_config = ConfigDict(frozen=True)

    id: str
    issue_id: Optional[str] = None
    author: Optional[JiraUser] = None
    update_author: Optional[JiraUser] = None
    time_spent: str = ""
    time_spent_seconds: int = 0
    comment: Optional[Any] = None
    started: Optional[str] = None
    created: Optional[str] = None
    updated: Optional[str] = None
    self_url: Optional[str] = None


class JiraResolution(BaseModel):
    """An issue resolution."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    name: str = ""
    description: Optional[str] = None
    self_url: Optional[str] = None
