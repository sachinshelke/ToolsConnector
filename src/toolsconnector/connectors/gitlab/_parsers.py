"""Internal response parsers for the GitLab connector.

Converts raw API JSON dicts into typed Pydantic models.
"""

from __future__ import annotations

from typing import Optional

from .types import (
    GitLabBranch,
    GitLabComment,
    GitLabIssue,
    GitLabJob,
    GitLabMilestone,
    GitLabNamespace,
    GitLabTag,
    GitLabUser,
    MergeRequest,
    Pipeline,
    Project,
)


def parse_user(data: Optional[dict]) -> Optional[GitLabUser]:
    """Safely parse a GitLabUser from API data."""
    if not data:
        return None
    return GitLabUser(
        id=data["id"],
        username=data["username"],
        name=data.get("name"),
        avatar_url=data.get("avatar_url"),
        web_url=data.get("web_url"),
        state=data.get("state", "active"),
    )


def parse_namespace(data: Optional[dict]) -> Optional[GitLabNamespace]:
    """Safely parse a GitLabNamespace from API data."""
    if not data:
        return None
    return GitLabNamespace(
        id=data["id"],
        name=data["name"],
        path=data["path"],
        kind=data.get("kind", "user"),
        full_path=data.get("full_path"),
        web_url=data.get("web_url"),
    )


def parse_milestone(data: Optional[dict]) -> Optional[GitLabMilestone]:
    """Safely parse a GitLabMilestone from API data."""
    if not data:
        return None
    return GitLabMilestone(
        id=data["id"],
        iid=data["iid"],
        title=data["title"],
        state=data.get("state", "active"),
        description=data.get("description"),
        due_date=data.get("due_date"),
    )


def parse_project(data: dict) -> Project:
    """Parse a single Project from API JSON."""
    return Project(
        id=data["id"],
        name=data["name"],
        name_with_namespace=data.get("name_with_namespace"),
        path=data["path"],
        path_with_namespace=data.get("path_with_namespace"),
        description=data.get("description"),
        visibility=data.get("visibility", "private"),
        web_url=data.get("web_url"),
        ssh_url_to_repo=data.get("ssh_url_to_repo"),
        http_url_to_repo=data.get("http_url_to_repo"),
        namespace=parse_namespace(data.get("namespace")),
        owner=parse_user(data.get("owner")),
        default_branch=data.get("default_branch", "main"),
        star_count=data.get("star_count", 0),
        forks_count=data.get("forks_count", 0),
        open_issues_count=data.get("open_issues_count", 0),
        archived=data.get("archived", False),
        created_at=data.get("created_at"),
        last_activity_at=data.get("last_activity_at"),
        topics=data.get("topics", []),
        empty_repo=data.get("empty_repo", False),
    )


def parse_issue(data: dict) -> GitLabIssue:
    """Parse a single GitLabIssue from API JSON."""
    return GitLabIssue(
        id=data["id"],
        iid=data["iid"],
        title=data["title"],
        description=data.get("description"),
        state=data.get("state", "opened"),
        web_url=data.get("web_url"),
        author=parse_user(data.get("author")),
        assignees=[parse_user(a) for a in data.get("assignees", []) if a],
        labels=data.get("labels", []),
        milestone=parse_milestone(data.get("milestone")),
        upvotes=data.get("upvotes", 0),
        downvotes=data.get("downvotes", 0),
        user_notes_count=data.get("user_notes_count", 0),
        confidential=data.get("confidential", False),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
        closed_at=data.get("closed_at"),
        due_date=data.get("due_date"),
    )


def parse_merge_request(data: dict) -> MergeRequest:
    """Parse a single MergeRequest from API JSON."""
    return MergeRequest(
        id=data["id"],
        iid=data["iid"],
        title=data["title"],
        description=data.get("description"),
        state=data.get("state", "opened"),
        web_url=data.get("web_url"),
        author=parse_user(data.get("author")),
        assignees=[parse_user(a) for a in data.get("assignees", []) if a],
        labels=data.get("labels", []),
        milestone=parse_milestone(data.get("milestone")),
        source_branch=data.get("source_branch"),
        target_branch=data.get("target_branch"),
        draft=data.get("draft", False),
        merge_status=data.get("merge_status"),
        merged_by=parse_user(data.get("merged_by")),
        merged_at=data.get("merged_at"),
        user_notes_count=data.get("user_notes_count", 0),
        upvotes=data.get("upvotes", 0),
        downvotes=data.get("downvotes", 0),
        has_conflicts=data.get("has_conflicts", False),
        changes_count=data.get("changes_count"),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
        closed_at=data.get("closed_at"),
    )


def parse_pipeline(data: dict) -> Pipeline:
    """Parse a single Pipeline from API JSON."""
    return Pipeline(
        id=data["id"],
        iid=data.get("iid"),
        project_id=data.get("project_id"),
        status=data.get("status", "created"),
        source=data.get("source"),
        ref=data.get("ref"),
        sha=data.get("sha"),
        web_url=data.get("web_url"),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
        started_at=data.get("started_at"),
        finished_at=data.get("finished_at"),
        duration=data.get("duration"),
        queued_duration=data.get("queued_duration"),
        coverage=data.get("coverage"),
        user=parse_user(data.get("user")),
    )


def parse_comment(data: dict) -> GitLabComment:
    """Parse a single GitLabComment (note) from API JSON."""
    return GitLabComment(
        id=data["id"],
        body=data.get("body", ""),
        author=parse_user(data.get("author")),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
        system=data.get("system", False),
        noteable_id=data.get("noteable_id"),
        noteable_type=data.get("noteable_type"),
        noteable_iid=data.get("noteable_iid"),
    )


def parse_job(data: dict) -> GitLabJob:
    """Parse a single GitLabJob from API JSON."""
    pipeline = data.get("pipeline", {})
    runner = data.get("runner") or {}
    return GitLabJob(
        id=data["id"],
        name=data.get("name", ""),
        status=data.get("status", "created"),
        stage=data.get("stage", ""),
        ref=data.get("ref"),
        tag=data.get("tag", False),
        coverage=data.get("coverage"),
        allow_failure=data.get("allow_failure", False),
        created_at=data.get("created_at"),
        started_at=data.get("started_at"),
        finished_at=data.get("finished_at"),
        duration=data.get("duration"),
        queued_duration=data.get("queued_duration"),
        web_url=data.get("web_url"),
        pipeline_id=pipeline.get("id") if pipeline else None,
        user=parse_user(data.get("user")),
        runner_name=runner.get("description"),
        failure_reason=data.get("failure_reason"),
    )


def parse_branch(data: dict) -> GitLabBranch:
    """Parse a single GitLabBranch from API JSON."""
    commit = data.get("commit", {})
    return GitLabBranch(
        name=data["name"],
        merged=data.get("merged", False),
        protected=data.get("protected", False),
        default=data.get("default", False),
        developers_can_push=data.get("developers_can_push", False),
        developers_can_merge=data.get("developers_can_merge", False),
        can_push=data.get("can_push", False),
        web_url=data.get("web_url"),
        commit_id=commit.get("id") if commit else None,
        commit_message=commit.get("message") if commit else None,
    )


def parse_tag(data: dict) -> GitLabTag:
    """Parse a single GitLabTag from API JSON."""
    commit = data.get("commit", {})
    release = data.get("release") or {}
    return GitLabTag(
        name=data["name"],
        message=data.get("message"),
        target=data.get("target"),
        protected=data.get("protected", False),
        release_description=release.get("description"),
        commit_id=commit.get("id") if commit else None,
        commit_message=commit.get("message") if commit else None,
    )
