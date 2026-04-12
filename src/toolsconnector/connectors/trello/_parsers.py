"""Trello API response parsers.

Helper functions to parse raw JSON dicts from the Trello REST API
into typed Pydantic models.
"""

from __future__ import annotations

from typing import Any

from .types import (
    TrelloAction,
    TrelloAttachment,
    TrelloBoard,
    TrelloCard,
    TrelloComment,
    TrelloLabel,
    TrelloList,
    TrelloMember,
)


def parse_member(data: dict[str, Any]) -> TrelloMember:
    """Parse a TrelloMember from API JSON.

    Args:
        data: Raw JSON dict from the Trello API.

    Returns:
        A TrelloMember instance.
    """
    return TrelloMember(
        id=data["id"],
        username=data.get("username"),
        full_name=data.get("fullName"),
        initials=data.get("initials"),
        avatar_url=data.get("avatarUrl"),
        url=data.get("url"),
    )


def parse_label(data: dict[str, Any]) -> TrelloLabel:
    """Parse a TrelloLabel from API JSON.

    Args:
        data: Raw JSON dict for a label.

    Returns:
        A TrelloLabel instance.
    """
    return TrelloLabel(
        id=data["id"],
        name=data.get("name"),
        color=data.get("color"),
    )


def parse_board(data: dict[str, Any]) -> TrelloBoard:
    """Parse a TrelloBoard from API JSON.

    Args:
        data: Raw JSON dict from the Trello API.

    Returns:
        A TrelloBoard instance.
    """
    return TrelloBoard(
        id=data["id"],
        name=data.get("name"),
        desc=data.get("desc"),
        closed=data.get("closed", False),
        url=data.get("url"),
        short_url=data.get("shortUrl"),
        id_organization=data.get("idOrganization"),
        memberships=data.get("memberships") or [],
    )


def parse_list(data: dict[str, Any]) -> TrelloList:
    """Parse a TrelloList from API JSON.

    Args:
        data: Raw JSON dict from the Trello API.

    Returns:
        A TrelloList instance.
    """
    return TrelloList(
        id=data["id"],
        name=data.get("name"),
        closed=data.get("closed", False),
        id_board=data.get("idBoard"),
        pos=data.get("pos"),
    )


def parse_card(data: dict[str, Any]) -> TrelloCard:
    """Parse a TrelloCard from API JSON.

    Args:
        data: Raw JSON dict from the Trello API.

    Returns:
        A TrelloCard instance.
    """
    labels_raw = data.get("labels") or []
    return TrelloCard(
        id=data["id"],
        name=data.get("name"),
        desc=data.get("desc"),
        closed=data.get("closed", False),
        id_board=data.get("idBoard"),
        id_list=data.get("idList"),
        url=data.get("url"),
        short_url=data.get("shortUrl"),
        pos=data.get("pos"),
        due=data.get("due"),
        due_complete=data.get("dueComplete", False),
        labels=[parse_label(lb) for lb in labels_raw],
        id_members=data.get("idMembers") or [],
        date_last_activity=data.get("dateLastActivity"),
    )


def parse_attachment(data: dict[str, Any]) -> TrelloAttachment:
    """Parse a TrelloAttachment from API JSON.

    Args:
        data: Raw JSON dict for an attachment.

    Returns:
        A TrelloAttachment instance.
    """
    return TrelloAttachment(
        id=data["id"],
        name=data.get("name"),
        url=data.get("url"),
        bytes=data.get("bytes"),
        date=data.get("date"),
        mime_type=data.get("mimeType"),
        is_upload=data.get("isUpload", False),
    )


def parse_action(data: dict[str, Any]) -> TrelloAction:
    """Parse a TrelloAction from API JSON.

    Args:
        data: Raw JSON dict for a card action.

    Returns:
        A TrelloAction instance.
    """
    member_raw = data.get("memberCreator")
    return TrelloAction(
        id=data["id"],
        type=data.get("type"),
        date=data.get("date"),
        id_member_creator=data.get("idMemberCreator"),
        data=data.get("data"),
        member_creator=parse_member(member_raw) if member_raw else None,
    )


def parse_comment(data: dict[str, Any]) -> TrelloComment:
    """Parse a TrelloComment from a Trello action JSON.

    Args:
        data: Raw JSON dict for a commentCard action.

    Returns:
        A TrelloComment instance.
    """
    action_data = data.get("data") or {}
    member_raw = data.get("memberCreator")
    return TrelloComment(
        id=data["id"],
        id_member_creator=data.get("idMemberCreator"),
        type=data.get("type", "commentCard"),
        date=data.get("date"),
        text=action_data.get("text"),
        member_creator=parse_member(member_raw) if member_raw else None,
    )
