"""Pydantic models for the Microsoft Teams (MS Graph) connector.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class Team(BaseModel):
    """A Microsoft Teams team."""

    model_config = ConfigDict(frozen=True)

    id: str
    display_name: str
    description: Optional[str] = None
    visibility: Optional[str] = None
    web_url: Optional[str] = None
    is_archived: bool = False


class TeamsChannel(BaseModel):
    """A channel within a Microsoft Teams team."""

    model_config = ConfigDict(frozen=True)

    id: str
    display_name: str
    description: Optional[str] = None
    membership_type: Optional[str] = None
    web_url: Optional[str] = None
    email: Optional[str] = None


class TeamsMessageBody(BaseModel):
    """The body content of a Teams message."""

    model_config = ConfigDict(frozen=True)

    content: Optional[str] = None
    content_type: str = "html"


class TeamsMessageFrom(BaseModel):
    """The sender information for a Teams message."""

    model_config = ConfigDict(frozen=True)

    display_name: Optional[str] = None
    user_id: Optional[str] = None


class TeamsMessage(BaseModel):
    """A message within a Teams channel."""

    model_config = ConfigDict(frozen=True)

    id: str
    body: Optional[TeamsMessageBody] = None
    from_user: Optional[TeamsMessageFrom] = None
    created_datetime: Optional[str] = None
    last_modified_datetime: Optional[str] = None
    subject: Optional[str] = None
    importance: str = "normal"
    web_url: Optional[str] = None
    attachments: list[dict] = Field(default_factory=list)


class TeamsMember(BaseModel):
    """A member of a Microsoft Teams team."""

    model_config = ConfigDict(frozen=True)

    id: str
    display_name: Optional[str] = None
    user_id: Optional[str] = None
    email: Optional[str] = None
    roles: list[str] = Field(default_factory=list)
