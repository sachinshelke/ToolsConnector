"""Pydantic models for X (Twitter) connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class XUser(BaseModel):
    """An X (Twitter) user.

    Returned by ``GET /2/users/me`` and other endpoints. Uses string IDs
    throughout — X user IDs are 64-bit integers transmitted as strings.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    name: str = ""
    username: str = ""
    description: str = ""
    verified: bool = False
    profile_image_url: str = ""
    created_at: Optional[str] = None
    public_metrics: dict[str, Any] = Field(default_factory=dict)


class Tweet(BaseModel):
    """An X (Twitter) tweet.

    The X API v2 returns rich entities (mentions, urls, hashtags,
    annotations) under ``entities``; we keep this as a free-form dict
    rather than modelling every nested shape.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    text: str = ""
    author_id: Optional[str] = None
    created_at: Optional[str] = None
    conversation_id: Optional[str] = None
    in_reply_to_user_id: Optional[str] = None
    lang: Optional[str] = None
    public_metrics: dict[str, Any] = Field(default_factory=dict)
    entities: dict[str, Any] = Field(default_factory=dict)
    referenced_tweets: list[dict[str, Any]] = Field(default_factory=list)
    edit_history_tweet_ids: list[str] = Field(default_factory=list)


class XDirectMessage(BaseModel):
    """An X direct message (Basic API tier or higher required to send)."""

    model_config = ConfigDict(frozen=True)

    dm_conversation_id: str
    dm_event_id: str = ""
