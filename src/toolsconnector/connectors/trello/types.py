"""Pydantic models for Trello connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Embedded / shared models
# ---------------------------------------------------------------------------


class TrelloMember(BaseModel):
    """A Trello member (user)."""

    model_config = ConfigDict(frozen=True)

    id: str
    username: Optional[str] = None
    full_name: Optional[str] = None
    initials: Optional[str] = None
    avatar_url: Optional[str] = None
    url: Optional[str] = None


class TrelloLabel(BaseModel):
    """A Trello label on a card."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: Optional[str] = None
    color: Optional[str] = None


# ---------------------------------------------------------------------------
# Top-level response models
# ---------------------------------------------------------------------------


class TrelloBoard(BaseModel):
    """A Trello board."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: Optional[str] = None
    desc: Optional[str] = None
    closed: bool = False
    url: Optional[str] = None
    short_url: Optional[str] = None
    id_organization: Optional[str] = None
    memberships: list[dict] = Field(default_factory=list)


class TrelloList(BaseModel):
    """A Trello list within a board."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: Optional[str] = None
    closed: bool = False
    id_board: Optional[str] = None
    pos: Optional[float] = None


class TrelloCard(BaseModel):
    """A Trello card."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: Optional[str] = None
    desc: Optional[str] = None
    closed: bool = False
    id_board: Optional[str] = None
    id_list: Optional[str] = None
    url: Optional[str] = None
    short_url: Optional[str] = None
    pos: Optional[float] = None
    due: Optional[str] = None
    due_complete: bool = False
    labels: list[TrelloLabel] = Field(default_factory=list)
    id_members: list[str] = Field(default_factory=list)
    date_last_activity: Optional[str] = None


class TrelloComment(BaseModel):
    """A comment (action) on a Trello card."""

    model_config = ConfigDict(frozen=True)

    id: str
    id_member_creator: Optional[str] = None
    type: str = "commentCard"
    date: Optional[str] = None
    text: Optional[str] = None
    member_creator: Optional[TrelloMember] = None
