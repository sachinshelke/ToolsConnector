"""Pydantic models for Slack connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Embedded / shared models
# ---------------------------------------------------------------------------


class SlackTopic(BaseModel):
    """Channel topic or purpose metadata."""

    model_config = ConfigDict(frozen=True)

    value: str = ""
    creator: str = ""
    last_set: int = 0


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class Channel(BaseModel):
    """Slack channel (public, private, or DM)."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str = ""
    is_channel: bool = False
    is_private: bool = False
    is_im: bool = False
    is_archived: bool = False
    is_member: bool = False
    topic: Optional[SlackTopic] = None
    purpose: Optional[SlackTopic] = None
    num_members: int = 0
    created: int = 0
    creator: str = ""


class Message(BaseModel):
    """Slack message."""

    model_config = ConfigDict(frozen=True)

    type: str = "message"
    subtype: Optional[str] = None
    ts: str = ""
    user: Optional[str] = None
    text: str = ""
    channel: Optional[str] = None
    thread_ts: Optional[str] = None
    reply_count: int = 0
    reactions: list[dict[str, Any]] = Field(default_factory=list)
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    blocks: list[dict[str, Any]] = Field(default_factory=list)


class SlackUser(BaseModel):
    """Slack workspace user."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str = ""
    real_name: str = ""
    display_name: str = ""
    email: Optional[str] = None
    is_bot: bool = False
    is_admin: bool = False
    is_owner: bool = False
    deleted: bool = False
    tz: Optional[str] = None
    avatar_url: Optional[str] = None


class SlackFile(BaseModel):
    """Slack uploaded file."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str = ""
    title: str = ""
    mimetype: str = ""
    filetype: str = ""
    size: int = 0
    url_private: str = ""
    permalink: str = ""
    channels: list[str] = Field(default_factory=list)
    created: int = 0
