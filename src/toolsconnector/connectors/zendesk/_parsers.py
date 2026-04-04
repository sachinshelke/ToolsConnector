"""Zendesk API response parsers.

Helper functions to parse raw JSON dicts from the Zendesk REST API
into typed Pydantic models.
"""

from __future__ import annotations

from typing import Any

from .types import ZendeskComment, ZendeskSearchResult, ZendeskTicket, ZendeskUser


def parse_user(data: dict[str, Any]) -> ZendeskUser:
    """Parse a ZendeskUser from API JSON.

    Args:
        data: Raw JSON dict from the Zendesk API.

    Returns:
        A ZendeskUser instance.
    """
    return ZendeskUser(
        id=data["id"],
        name=data.get("name"),
        email=data.get("email"),
        role=data.get("role"),
        active=data.get("active", True),
        verified=data.get("verified", False),
        phone=data.get("phone"),
        organization_id=data.get("organization_id"),
        time_zone=data.get("time_zone"),
        locale=data.get("locale"),
        tags=data.get("tags") or [],
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
        url=data.get("url"),
    )


def parse_comment(data: dict[str, Any]) -> ZendeskComment:
    """Parse a ZendeskComment from API JSON.

    Args:
        data: Raw JSON dict from the Zendesk API.

    Returns:
        A ZendeskComment instance.
    """
    return ZendeskComment(
        id=data["id"],
        type=data.get("type"),
        body=data.get("body"),
        html_body=data.get("html_body"),
        plain_body=data.get("plain_body"),
        public=data.get("public", True),
        author_id=data.get("author_id"),
        created_at=data.get("created_at"),
    )


def parse_ticket(data: dict[str, Any]) -> ZendeskTicket:
    """Parse a ZendeskTicket from API JSON.

    Args:
        data: Raw JSON dict from the Zendesk API.

    Returns:
        A ZendeskTicket instance.
    """
    via = data.get("via") or {}
    return ZendeskTicket(
        id=data["id"],
        subject=data.get("subject"),
        description=data.get("description"),
        status=data.get("status"),
        priority=data.get("priority"),
        type=data.get("type"),
        requester_id=data.get("requester_id"),
        submitter_id=data.get("submitter_id"),
        assignee_id=data.get("assignee_id"),
        organization_id=data.get("organization_id"),
        group_id=data.get("group_id"),
        tags=data.get("tags") or [],
        via_channel=via.get("channel"),
        url=data.get("url"),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
    )


def parse_search_result(data: dict[str, Any]) -> ZendeskSearchResult:
    """Parse a ZendeskSearchResult from API JSON.

    Args:
        data: Raw JSON dict from the search results.

    Returns:
        A ZendeskSearchResult instance.
    """
    return ZendeskSearchResult(
        id=data["id"],
        result_type=data.get("result_type"),
        url=data.get("url"),
        subject=data.get("subject"),
        name=data.get("name"),
        description=data.get("description"),
        status=data.get("status"),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
    )
