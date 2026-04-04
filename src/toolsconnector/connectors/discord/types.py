"""Pydantic models for Discord connector types.

All response models use ``frozen=True`` to enforce immutability.
Discord uses snowflake IDs represented as strings.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Embedded / shared models
# ---------------------------------------------------------------------------


class Embed(BaseModel):
    """Discord message embed object.

    See https://discord.com/developers/docs/resources/message#embed-object
    """

    model_config = ConfigDict(frozen=True)

    title: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    color: Optional[int] = None
    timestamp: Optional[str] = None
    footer: Optional[dict[str, Any]] = None
    image: Optional[dict[str, Any]] = None
    thumbnail: Optional[dict[str, Any]] = None
    author: Optional[dict[str, Any]] = None
    fields: Optional[list[dict[str, Any]]] = None


class DiscordUser(BaseModel):
    """Discord user."""

    model_config = ConfigDict(frozen=True)

    id: str
    username: str = ""
    discriminator: str = "0"
    global_name: Optional[str] = None
    avatar: Optional[str] = None
    bot: bool = False
    system: bool = False
    banner: Optional[str] = None
    accent_color: Optional[int] = None


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class DiscordChannel(BaseModel):
    """Discord channel (text, voice, category, etc.)."""

    model_config = ConfigDict(frozen=True)

    id: str
    type: int = 0
    guild_id: Optional[str] = None
    name: Optional[str] = None
    topic: Optional[str] = None
    position: int = 0
    nsfw: bool = False
    parent_id: Optional[str] = None
    rate_limit_per_user: int = 0
    permission_overwrites: list[dict[str, Any]] = Field(default_factory=list)


class DiscordMessage(BaseModel):
    """Discord message."""

    model_config = ConfigDict(frozen=True)

    id: str
    channel_id: str = ""
    guild_id: Optional[str] = None
    author: Optional[DiscordUser] = None
    content: str = ""
    timestamp: str = ""
    edited_timestamp: Optional[str] = None
    tts: bool = False
    mention_everyone: bool = False
    mentions: list[DiscordUser] = Field(default_factory=list)
    pinned: bool = False
    type: int = 0
    embeds: list[Embed] = Field(default_factory=list)
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    reactions: list[dict[str, Any]] = Field(default_factory=list)


class GuildMember(BaseModel):
    """Discord guild (server) member."""

    model_config = ConfigDict(frozen=True)

    user: Optional[DiscordUser] = None
    nick: Optional[str] = None
    roles: list[str] = Field(default_factory=list)
    joined_at: str = ""
    deaf: bool = False
    mute: bool = False
    avatar: Optional[str] = None
    pending: bool = False
