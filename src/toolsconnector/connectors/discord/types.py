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


class DiscordRole(BaseModel):
    """Discord guild role.

    See https://discord.com/developers/docs/topics/permissions#role-object
    """

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    color: int = 0
    hoist: bool = False
    position: int = 0
    permissions: str = "0"
    managed: bool = False
    mentionable: bool = False
    icon: Optional[str] = None
    unicode_emoji: Optional[str] = None


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


class DiscordGuild(BaseModel):
    """Discord guild (server).

    See https://discord.com/developers/docs/resources/guild#guild-object
    """

    model_config = ConfigDict(frozen=True)

    id: str
    name: str = ""
    icon: Optional[str] = None
    description: Optional[str] = None
    owner_id: str = ""
    region: Optional[str] = None
    afk_channel_id: Optional[str] = None
    afk_timeout: int = 0
    verification_level: int = 0
    default_message_notifications: int = 0
    explicit_content_filter: int = 0
    roles: list[DiscordRole] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    member_count: Optional[int] = None
    max_members: Optional[int] = None
    premium_tier: int = 0
    premium_subscription_count: int = 0
    preferred_locale: str = "en-US"
    banner: Optional[str] = None
    vanity_url_code: Optional[str] = None
    nsfw_level: int = 0


class DiscordWebhook(BaseModel):
    """Discord webhook.

    See https://discord.com/developers/docs/resources/webhook#webhook-object
    """

    model_config = ConfigDict(frozen=True)

    id: str
    type: int = 1
    guild_id: Optional[str] = None
    channel_id: Optional[str] = None
    name: Optional[str] = None
    avatar: Optional[str] = None
    token: Optional[str] = None
    url: Optional[str] = None
    user: Optional[DiscordUser] = None
