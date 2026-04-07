"""Pydantic models for Telegram Bot API connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class TelegramUser(BaseModel):
    """A Telegram user or bot account."""

    model_config = ConfigDict(frozen=True)

    id: int = 0
    is_bot: bool = False
    first_name: str = ""
    last_name: Optional[str] = None
    username: Optional[str] = None
    language_code: Optional[str] = None


class TelegramChat(BaseModel):
    """A Telegram chat (private, group, supergroup, or channel)."""

    model_config = ConfigDict(frozen=True)

    id: int = 0
    type: str = ""
    title: Optional[str] = None
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    description: Optional[str] = None
    invite_link: Optional[str] = None
    photo: Optional[dict[str, Any]] = None
    pinned_message: Optional[dict[str, Any]] = None


class TelegramMessage(BaseModel):
    """A Telegram message."""

    model_config = ConfigDict(frozen=True)

    message_id: int = 0
    date: int = 0
    chat: Optional[TelegramChat] = None
    from_user: Optional[TelegramUser] = Field(None, alias="from")
    text: Optional[str] = None
    caption: Optional[str] = None
    photo: Optional[list[dict[str, Any]]] = None
    document: Optional[dict[str, Any]] = None
    reply_to_message: Optional[dict[str, Any]] = None
    edit_date: Optional[int] = None
    entities: list[dict[str, Any]] = Field(default_factory=list)


class TelegramUpdate(BaseModel):
    """A Telegram update event."""

    model_config = ConfigDict(frozen=True)

    update_id: int = 0
    message: Optional[TelegramMessage] = None
    edited_message: Optional[TelegramMessage] = None
    channel_post: Optional[TelegramMessage] = None
    callback_query: Optional[dict[str, Any]] = None


class TelegramWebhookInfo(BaseModel):
    """Information about the current webhook configuration."""

    model_config = ConfigDict(frozen=True)

    url: str = ""
    has_custom_certificate: bool = False
    pending_update_count: int = 0
    ip_address: Optional[str] = None
    last_error_date: Optional[int] = None
    last_error_message: Optional[str] = None
    max_connections: Optional[int] = None
    allowed_updates: Optional[list[str]] = None
