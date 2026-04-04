"""GitLab connector — projects, issues, merge requests, and CI/CD pipelines."""

from __future__ import annotations

from .connector import GitLab
from .types import (
    GitLabIssue,
    GitLabLabel,
    GitLabMilestone,
    GitLabNamespace,
    GitLabUser,
    MergeRequest,
    Pipeline,
    Project,
)

__all__ = [
    "GitLab",
    "GitLabIssue",
    "GitLabLabel",
    "GitLabMilestone",
    "GitLabNamespace",
    "GitLabUser",
    "MergeRequest",
    "Pipeline",
    "Project",
]
