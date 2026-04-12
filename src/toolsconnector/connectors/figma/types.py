"""Pydantic models for Figma connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Embedded / shared models
# ---------------------------------------------------------------------------


class FigmaUser(BaseModel):
    """A Figma user reference."""

    model_config = ConfigDict(frozen=True)

    id: Optional[str] = None
    handle: Optional[str] = None
    img_url: Optional[str] = None


class FigmaClientMeta(BaseModel):
    """Positional metadata for a Figma comment."""

    model_config = ConfigDict(frozen=True)

    x: Optional[float] = None
    y: Optional[float] = None
    node_id: Optional[str] = None
    node_offset: Optional[dict[str, float]] = None


# ---------------------------------------------------------------------------
# Top-level response models
# ---------------------------------------------------------------------------


class FigmaFile(BaseModel):
    """A Figma file (design document)."""

    model_config = ConfigDict(frozen=True)

    name: Optional[str] = None
    last_modified: Optional[str] = None
    thumbnail_url: Optional[str] = None
    version: Optional[str] = None
    role: Optional[str] = None
    editor_type: Optional[str] = None
    schema_version: Optional[int] = None


class FigmaVersion(BaseModel):
    """A version history entry for a Figma file."""

    model_config = ConfigDict(frozen=True)

    id: str
    created_at: Optional[str] = None
    label: Optional[str] = None
    description: Optional[str] = None
    user: Optional[FigmaUser] = None


class FigmaComment(BaseModel):
    """A comment on a Figma file."""

    model_config = ConfigDict(frozen=True)

    id: str
    message: Optional[str] = None
    file_key: Optional[str] = None
    parent_id: Optional[str] = None
    user: Optional[FigmaUser] = None
    created_at: Optional[str] = None
    resolved_at: Optional[str] = None
    order_id: Optional[str] = None
    client_meta: Optional[FigmaClientMeta] = None


class FigmaProject(BaseModel):
    """A Figma project within a team."""

    model_config = ConfigDict(frozen=True)

    id: int
    name: Optional[str] = None


class FigmaProjectFile(BaseModel):
    """A file entry within a Figma project listing."""

    model_config = ConfigDict(frozen=True)

    key: str
    name: Optional[str] = None
    thumbnail_url: Optional[str] = None
    last_modified: Optional[str] = None


class FigmaComponent(BaseModel):
    """A component within a Figma file."""

    model_config = ConfigDict(frozen=True)

    key: str
    name: Optional[str] = None
    description: Optional[str] = None
    file_key: Optional[str] = None
    node_id: Optional[str] = None
    thumbnail_url: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    user: Optional[FigmaUser] = None


class FigmaStyle(BaseModel):
    """A published style in a Figma file or team library."""

    model_config = ConfigDict(frozen=True)

    key: str
    name: Optional[str] = None
    description: Optional[str] = None
    style_type: Optional[str] = None
    file_key: Optional[str] = None
    node_id: Optional[str] = None
    thumbnail_url: Optional[str] = None
    sort_position: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    user: Optional[FigmaUser] = None


class FigmaPage(BaseModel):
    """A page (canvas) within a Figma file."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: Optional[str] = None
    type: str = "CANVAS"


class FigmaComponentSet(BaseModel):
    """A component set (variant group) in a Figma file."""

    model_config = ConfigDict(frozen=True)

    key: str
    name: Optional[str] = None
    description: Optional[str] = None
    file_key: Optional[str] = None
    node_id: Optional[str] = None
    thumbnail_url: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    user: Optional[FigmaUser] = None


class FigmaImage(BaseModel):
    """An exported image reference from Figma."""

    model_config = ConfigDict(frozen=True)

    node_id: str
    image_url: Optional[str] = None
    error: Optional[str] = None
