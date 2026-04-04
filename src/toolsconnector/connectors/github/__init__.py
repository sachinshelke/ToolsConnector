"""GitHub connector — repositories, issues, PRs, commits, and code search."""

from __future__ import annotations

from .connector import GitHub
from .types import (
    CodeSearchResult,
    Comment,
    Commit,
    CommitAuthor,
    CommitDetail,
    GitHubLabel,
    GitHubMilestone,
    GitHubUser,
    Issue,
    PullRequest,
    Repository,
)

__all__ = [
    "GitHub",
    "CodeSearchResult",
    "Comment",
    "Commit",
    "CommitAuthor",
    "CommitDetail",
    "GitHubLabel",
    "GitHubMilestone",
    "GitHubUser",
    "Issue",
    "PullRequest",
    "Repository",
]
