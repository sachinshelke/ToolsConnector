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


class Reaction(BaseModel):
    """A reaction on a Slack message."""

    model_config = ConfigDict(frozen=True)

    name: str
    count: int = 0
    users: list[str] = Field(default_factory=list)


class PinnedItem(BaseModel):
    """A pinned item in a Slack channel."""

    model_config = ConfigDict(frozen=True)

    type: str = ""
    channel: Optional[str] = None
    message: Optional[dict[str, Any]] = None
    file: Optional[dict[str, Any]] = None
    created: int = 0
    created_by: Optional[str] = None


class Reminder(BaseModel):
    """A Slack reminder."""

    model_config = ConfigDict(frozen=True)

    id: str
    creator: str = ""
    text: str = ""
    user: str = ""
    recurring: bool = False
    time: Optional[int] = None
    complete_ts: Optional[int] = None


class ScheduledMessage(BaseModel):
    """A scheduled message in Slack."""

    model_config = ConfigDict(frozen=True)

    id: str
    channel_id: str = ""
    post_at: int = 0
    date_created: int = 0
    text: str = ""


class UserPresence(BaseModel):
    """Slack user presence information."""

    model_config = ConfigDict(frozen=True)

    presence: str = "away"  # "active" or "away"
    online: bool = False
    auto_away: bool = False
    manual_away: bool = False
    last_activity: Optional[int] = None


class UserProfile(BaseModel):
    """Slack user profile with extended fields."""

    model_config = ConfigDict(frozen=True)

    status_text: str = ""
    status_emoji: str = ""
    status_expiration: int = 0
    real_name: str = ""
    display_name: str = ""
    email: Optional[str] = None
    first_name: str = ""
    last_name: str = ""
    title: str = ""
    phone: str = ""
    image_72: str = ""
    image_192: str = ""


class Bookmark(BaseModel):
    """A bookmark in a Slack channel."""

    model_config = ConfigDict(frozen=True)

    id: str
    channel_id: str = ""
    title: str = ""
    link: str = ""
    emoji: str = ""
    type: str = "link"
    created: int = 0
    updated: int = 0


class SearchResult(BaseModel):
    """A search result from Slack."""

    model_config = ConfigDict(frozen=True)

    channel: Optional[dict[str, Any]] = None
    ts: str = ""
    text: str = ""
    user: Optional[str] = None
    permalink: str = ""
    score: Optional[float] = None


class CustomEmoji(BaseModel):
    """A custom emoji in the workspace."""

    model_config = ConfigDict(frozen=True)

    name: str
    url: str = ""
    alias_for: Optional[str] = None
