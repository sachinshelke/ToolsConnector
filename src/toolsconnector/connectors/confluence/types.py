"""Pydantic models for the Confluence (Atlassian Cloud v2 API) connector.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ConfluenceSpace(BaseModel):
    """A Confluence space."""

    model_config = ConfigDict(frozen=True)

    id: str
    key: Optional[str] = None
    name: str
    type: Optional[str] = None
    status: Optional[str] = None
    description: Optional[str] = None
    homepage_id: Optional[str] = None


class ConfluenceVersion(BaseModel):
    """Version information for a Confluence page."""

    model_config = ConfigDict(frozen=True)

    number: int
    message: Optional[str] = None
    created_at: Optional[str] = None


class ConfluencePage(BaseModel):
    """A Confluence page."""

    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    space_id: Optional[str] = None
    status: str = "current"
    body_storage: Optional[str] = None
    parent_id: Optional[str] = None
    version: Optional[ConfluenceVersion] = None
    created_at: Optional[str] = None
    author_id: Optional[str] = None
    web_url: Optional[str] = None


class ConfluenceComment(BaseModel):
    """A comment on a Confluence page."""

    model_config = ConfigDict(frozen=True)

    id: str
    body_storage: Optional[str] = None
    created_at: Optional[str] = None
    author_id: Optional[str] = None
    version: Optional[ConfluenceVersion] = None


class ConfluenceLabel(BaseModel):
    """A label attached to a Confluence page."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    name: str = ""
    prefix: Optional[str] = None
