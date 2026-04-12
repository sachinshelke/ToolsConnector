"""Jira API response parsers.

Helper functions to parse raw JSON dicts from the Jira REST API
into typed Pydantic models.
"""

from __future__ import annotations

from typing import Any, Optional

from .types import (
    JiraComment,
    JiraIssue,
    JiraIssueType,
    JiraPriority,
    JiraProject,
    JiraResolution,
    JiraStatus,
    JiraUser,
    JiraWorklog,
)


def parse_user(data: Optional[dict[str, Any]]) -> Optional[JiraUser]:
    """Parse a Jira user JSON fragment.

    Args:
        data: Raw user JSON dict from the Jira API, or None.

    Returns:
        JiraUser instance or None if data is empty.
    """
    if not data:
        return None
    return JiraUser(
        account_id=data.get("accountId", ""),
        display_name=data.get("displayName"),
        email_address=data.get("emailAddress"),
        active=data.get("active", True),
        avatar_url=(data.get("avatarUrls") or {}).get("48x48"),
    )


def parse_priority(data: Optional[dict[str, Any]]) -> Optional[JiraPriority]:
    """Parse a priority JSON fragment.

    Args:
        data: Raw priority JSON dict, or None.

    Returns:
        JiraPriority instance or None.
    """
    if not data:
        return None
    return JiraPriority(
        id=data.get("id", ""),
        name=data.get("name", ""),
        icon_url=data.get("iconUrl"),
    )


def parse_status(data: Optional[dict[str, Any]]) -> Optional[JiraStatus]:
    """Parse a status JSON fragment.

    Args:
        data: Raw status JSON dict, or None.

    Returns:
        JiraStatus instance or None.
    """
    if not data:
        return None
    category = data.get("statusCategory", {})
    return JiraStatus(
        id=data.get("id", ""),
        name=data.get("name", ""),
        category_key=category.get("key"),
    )


def parse_issue_type(data: Optional[dict[str, Any]]) -> Optional[JiraIssueType]:
    """Parse an issue-type JSON fragment.

    Args:
        data: Raw issue type JSON dict, or None.

    Returns:
        JiraIssueType instance or None.
    """
    if not data:
        return None
    return JiraIssueType(
        id=data.get("id", ""),
        name=data.get("name", ""),
        subtask=data.get("subtask", False),
        icon_url=data.get("iconUrl"),
    )


def parse_issue(data: dict[str, Any]) -> JiraIssue:
    """Parse a raw Jira issue JSON into a JiraIssue model.

    Args:
        data: Raw issue JSON dict from the Jira API.

    Returns:
        JiraIssue instance.
    """
    fields = data.get("fields", {})
    components = [c.get("name", "") for c in fields.get("components", [])]
    fix_versions = [v.get("name", "") for v in fields.get("fixVersions", [])]
    project = fields.get("project", {})

    return JiraIssue(
        id=data["id"],
        key=data["key"],
        self_url=data.get("self"),
        summary=fields.get("summary", ""),
        description=fields.get("description"),
        status=parse_status(fields.get("status")),
        issue_type=parse_issue_type(fields.get("issuetype")),
        priority=parse_priority(fields.get("priority")),
        assignee=parse_user(fields.get("assignee")),
        reporter=parse_user(fields.get("reporter")),
        project_key=project.get("key", ""),
        created=fields.get("created"),
        updated=fields.get("updated"),
        labels=fields.get("labels", []),
        components=components,
        fix_versions=fix_versions,
    )


def parse_project(data: dict[str, Any]) -> JiraProject:
    """Parse a raw Jira project JSON into a JiraProject model.

    Args:
        data: Raw project JSON dict from the Jira API.

    Returns:
        JiraProject instance.
    """
    return JiraProject(
        id=data.get("id", ""),
        key=data.get("key", ""),
        name=data.get("name", ""),
        project_type_key=data.get("projectTypeKey"),
        lead=parse_user(data.get("lead")),
        avatar_url=(data.get("avatarUrls") or {}).get("48x48"),
        self_url=data.get("self"),
    )


def parse_comment(data: dict[str, Any]) -> JiraComment:
    """Parse a Jira comment JSON into a JiraComment model.

    Args:
        data: Raw comment JSON dict from the Jira API.

    Returns:
        JiraComment instance.
    """
    return JiraComment(
        id=data.get("id", ""),
        body=data.get("body"),
        author=parse_user(data.get("author")),
        created=data.get("created"),
        updated=data.get("updated"),
        self_url=data.get("self"),
    )


def parse_worklog(data: dict[str, Any]) -> JiraWorklog:
    """Parse a Jira worklog JSON into a JiraWorklog model.

    Args:
        data: Raw worklog JSON dict from the Jira API.

    Returns:
        JiraWorklog instance.
    """
    return JiraWorklog(
        id=data.get("id", ""),
        issue_id=data.get("issueId"),
        author=parse_user(data.get("author")),
        update_author=parse_user(data.get("updateAuthor")),
        time_spent=data.get("timeSpent", ""),
        time_spent_seconds=data.get("timeSpentSeconds", 0),
        comment=data.get("comment"),
        started=data.get("started"),
        created=data.get("created"),
        updated=data.get("updated"),
        self_url=data.get("self"),
    )


def parse_resolution(data: dict[str, Any]) -> JiraResolution:
    """Parse a Jira resolution JSON into a JiraResolution model.

    Args:
        data: Raw resolution JSON dict from the Jira API.

    Returns:
        JiraResolution instance.
    """
    return JiraResolution(
        id=data.get("id", ""),
        name=data.get("name", ""),
        description=data.get("description"),
        self_url=data.get("self"),
    )
