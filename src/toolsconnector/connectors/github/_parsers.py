"""Internal response parsers for the GitHub connector.

Converts raw API JSON dicts into typed Pydantic models.
"""

from __future__ import annotations

import re
from typing import Optional

from .types import (
    Branch,
    CodeSearchResult,
    Comment,
    Commit,
    CommitAuthor,
    CommitDetail,
    FileContent,
    GitHubGist,
    GitHubLabel,
    GitHubMilestone,
    GitHubUser,
    Issue,
    Release,
    Repository,
    Workflow,
    WorkflowRun,
)

_LINK_RE = re.compile(r'<([^>]+)>;\s*rel="(\w+)"')


def parse_link_header(header: Optional[str]) -> dict[str, str]:
    """Parse a GitHub ``Link`` header into a dict of rel -> url.

    Args:
        header: Raw Link header value.

    Returns:
        Mapping of rel names to URLs.
    """
    if not header:
        return {}
    return {rel: url for url, rel in _LINK_RE.findall(header)}


def parse_user(data: Optional[dict]) -> Optional[GitHubUser]:
    """Safely parse a GitHubUser from API data."""
    if not data:
        return None
    return GitHubUser(
        login=data["login"],
        id=data["id"],
        avatar_url=data.get("avatar_url"),
        html_url=data.get("html_url"),
        type=data.get("type", "User"),
        site_admin=data.get("site_admin", False),
    )


def parse_labels(items: list[dict]) -> list[GitHubLabel]:
    """Parse a list of label dicts."""
    return [
        GitHubLabel(
            id=lb["id"],
            name=lb["name"],
            color=lb.get("color", ""),
            description=lb.get("description"),
        )
        for lb in items
    ]


def parse_repo(data: dict) -> Repository:
    """Parse a single Repository from API JSON."""
    return Repository(
        id=data["id"],
        name=data["name"],
        full_name=data["full_name"],
        owner=parse_user(data.get("owner")),
        private=data.get("private", False),
        html_url=data.get("html_url"),
        description=data.get("description"),
        fork=data.get("fork", False),
        language=data.get("language"),
        default_branch=data.get("default_branch", "main"),
        stargazers_count=data.get("stargazers_count", 0),
        watchers_count=data.get("watchers_count", 0),
        forks_count=data.get("forks_count", 0),
        open_issues_count=data.get("open_issues_count", 0),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
        pushed_at=data.get("pushed_at"),
        archived=data.get("archived", False),
        disabled=data.get("disabled", False),
        topics=data.get("topics", []),
        visibility=data.get("visibility", "public"),
    )


def parse_issue(data: dict) -> Issue:
    """Parse a single Issue from API JSON."""
    return Issue(
        id=data["id"],
        number=data["number"],
        title=data["title"],
        body=data.get("body"),
        state=data.get("state", "open"),
        html_url=data.get("html_url"),
        user=parse_user(data.get("user")),
        labels=parse_labels(data.get("labels", [])),
        assignees=[parse_user(a) for a in data.get("assignees", []) if a],
        milestone=(
            GitHubMilestone(
                id=data["milestone"]["id"],
                number=data["milestone"]["number"],
                title=data["milestone"]["title"],
                state=data["milestone"].get("state", "open"),
                description=data["milestone"].get("description"),
            )
            if data.get("milestone")
            else None
        ),
        comments=data.get("comments", 0),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
        closed_at=data.get("closed_at"),
        locked=data.get("locked", False),
    )


def parse_comment(data: dict) -> Comment:
    """Parse a single Comment from API JSON."""
    return Comment(
        id=data["id"],
        body=data["body"],
        user=parse_user(data.get("user")),
        html_url=data.get("html_url"),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
    )


def parse_commit(data: dict) -> Commit:
    """Parse a single Commit from API JSON."""
    commit_data = data.get("commit", {})
    author_data = commit_data.get("author")
    committer_data = commit_data.get("committer")
    return Commit(
        sha=data["sha"],
        commit=CommitDetail(
            message=commit_data.get("message", ""),
            author=(
                CommitAuthor(
                    name=author_data.get("name"),
                    email=author_data.get("email"),
                    date=author_data.get("date"),
                )
                if author_data
                else None
            ),
            committer=(
                CommitAuthor(
                    name=committer_data.get("name"),
                    email=committer_data.get("email"),
                    date=committer_data.get("date"),
                )
                if committer_data
                else None
            ),
        ),
        author=parse_user(data.get("author")),
        committer=parse_user(data.get("committer")),
        html_url=data.get("html_url"),
    )


def parse_code_search_result(item: dict) -> CodeSearchResult:
    """Parse a single CodeSearchResult from the search API response."""
    return CodeSearchResult(
        name=item["name"],
        path=item["path"],
        sha=item["sha"],
        html_url=item.get("html_url"),
        repository=(parse_repo(item["repository"]) if item.get("repository") else None),
        score=item.get("score", 0.0),
        text_matches=item.get("text_matches", []),
    )


def parse_branch(data: dict) -> Branch:
    """Parse a single Branch from API JSON."""
    commit = data.get("commit", {})
    return Branch(
        name=data["name"],
        sha=commit.get("sha", ""),
        protected=data.get("protected", False),
    )


def parse_release(data: dict) -> Release:
    """Parse a single Release from API JSON."""
    return Release(
        id=data["id"],
        tag_name=data["tag_name"],
        name=data.get("name"),
        body=data.get("body"),
        draft=data.get("draft", False),
        prerelease=data.get("prerelease", False),
        html_url=data.get("html_url"),
        author=parse_user(data.get("author")),
        created_at=data.get("created_at"),
        published_at=data.get("published_at"),
        tarball_url=data.get("tarball_url"),
        zipball_url=data.get("zipball_url"),
    )


def parse_file_content(data: dict) -> FileContent:
    """Parse a single FileContent from API JSON."""
    return FileContent(
        type=data.get("type", "file"),
        name=data.get("name", ""),
        path=data.get("path", ""),
        sha=data.get("sha", ""),
        size=data.get("size", 0),
        content=data.get("content"),
        encoding=data.get("encoding"),
        html_url=data.get("html_url"),
        download_url=data.get("download_url"),
    )


def parse_workflow(data: dict) -> Workflow:
    """Parse a single Workflow from API JSON."""
    return Workflow(
        id=data["id"],
        name=data.get("name", ""),
        path=data.get("path", ""),
        state=data.get("state", "active"),
        html_url=data.get("html_url"),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
    )


def parse_workflow_run(data: dict) -> WorkflowRun:
    """Parse a single WorkflowRun from API JSON."""
    return WorkflowRun(
        id=data["id"],
        name=data.get("name"),
        head_branch=data.get("head_branch"),
        head_sha=data.get("head_sha", ""),
        status=data.get("status"),
        conclusion=data.get("conclusion"),
        workflow_id=data.get("workflow_id", 0),
        html_url=data.get("html_url"),
        run_number=data.get("run_number", 0),
        event=data.get("event", ""),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
        actor=parse_user(data.get("actor")),
    )


def parse_gist(data: dict) -> GitHubGist:
    """Parse a single GitHubGist from API JSON."""
    return GitHubGist(
        id=data["id"],
        description=data.get("description"),
        public=data.get("public", True),
        html_url=data.get("html_url"),
        files=data.get("files", {}),
        owner=parse_user(data.get("owner")),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
        comments=data.get("comments", 0),
    )
