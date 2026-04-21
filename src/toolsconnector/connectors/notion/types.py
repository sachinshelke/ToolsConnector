"""Pydantic models for Notion connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Embedded / shared models
# ---------------------------------------------------------------------------


class NotionUser(BaseModel):
    """A Notion user reference."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    type: str = "person"


class NotionRichText(BaseModel):
    """A single rich-text segment in Notion."""

    model_config = ConfigDict(frozen=True)

    type: str = "text"
    plain_text: str = ""
    href: Optional[str] = None
    annotations: dict[str, Any] = Field(default_factory=dict)


class NotionProperty(BaseModel):
    """A property value on a Notion page or database.

    The ``type`` field indicates which value key is populated
    (e.g., ``"title"``, ``"rich_text"``, ``"number"``).
    """

    model_config = ConfigDict(frozen=True)

    id: str = ""
    type: str = ""
    title: Optional[list[NotionRichText]] = None
    rich_text: Optional[list[NotionRichText]] = None
    number: Optional[float] = None
    select: Optional[dict[str, Any]] = None
    multi_select: Optional[list[dict[str, Any]]] = None
    date: Optional[dict[str, Any]] = None
    checkbox: Optional[bool] = None
    url: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    formula: Optional[dict[str, Any]] = None
    relation: Optional[list[dict[str, str]]] = None
    rollup: Optional[dict[str, Any]] = None
    people: Optional[list[NotionUser]] = None
    files: Optional[list[dict[str, Any]]] = None
    status: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Top-level response models
# ---------------------------------------------------------------------------


class NotionPage(BaseModel):
    """A Notion page object."""

    model_config = ConfigDict(frozen=True)

    id: str
    object: str = "page"
    created_time: Optional[str] = None
    last_edited_time: Optional[str] = None
    created_by: Optional[NotionUser] = None
    last_edited_by: Optional[NotionUser] = None
    archived: bool = False
    url: Optional[str] = None
    parent: dict[str, Any] = Field(default_factory=dict)
    properties: dict[str, NotionProperty] = Field(default_factory=dict)
    icon: Optional[dict[str, Any]] = None
    cover: Optional[dict[str, Any]] = None


class NotionDatabase(BaseModel):
    """A Notion database object."""

    model_config = ConfigDict(frozen=True)

    id: str
    object: str = "database"
    title: list[NotionRichText] = Field(default_factory=list)
    description: list[NotionRichText] = Field(default_factory=list)
    created_time: Optional[str] = None
    last_edited_time: Optional[str] = None
    archived: bool = False
    url: Optional[str] = None
    parent: dict[str, Any] = Field(default_factory=dict)
    properties: dict[str, dict[str, Any]] = Field(default_factory=dict)
    icon: Optional[dict[str, Any]] = None
    cover: Optional[dict[str, Any]] = None
    is_inline: bool = False


class NotionBlock(BaseModel):
    """A Notion block (content element)."""

    model_config = ConfigDict(frozen=True)

    id: str
    object: str = "block"
    type: str = ""
    created_time: Optional[str] = None
    last_edited_time: Optional[str] = None
    created_by: Optional[NotionUser] = None
    last_edited_by: Optional[NotionUser] = None
    archived: bool = False
    has_children: bool = False
    parent: dict[str, Any] = Field(default_factory=dict)
    content: dict[str, Any] = Field(default_factory=dict)


class NotionComment(BaseModel):
    """A Notion comment on a page or block."""

    model_config = ConfigDict(frozen=True)

    id: str
    object: str = "comment"
    parent: dict[str, Any] = Field(default_factory=dict)
    discussion_id: Optional[str] = None
    created_time: Optional[str] = None
    last_edited_time: Optional[str] = None
    created_by: Optional[NotionUser] = None
    rich_text: list[NotionRichText] = Field(default_factory=list)
