"""GitLab connector — projects, issues, merge requests, and CI/CD pipelines."""

from __future__ import annotations

from .connector import GitLab
from .types import (
    GitLabBranch,
    GitLabComment,
    GitLabIssue,
    GitLabJob,
    GitLabLabel,
    GitLabMember,
    GitLabMilestone,
    GitLabNamespace,
    GitLabTag,
    GitLabUser,
    MergeRequest,
    Pipeline,
    Project,
)

__all__ = [
    "GitLab",
    "GitLabBranch",
    "GitLabComment",
    "GitLabIssue",
    "GitLabJob",
    "GitLabLabel",
    "GitLabMember",
    "GitLabMilestone",
    "GitLabNamespace",
    "GitLabTag",
    "GitLabUser",
    "MergeRequest",
    "Pipeline",
    "Project",
]
