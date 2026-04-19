"""Pydantic models for Medium connector types.

All response models use ``frozen=True`` to enforce immutability and
``populate_by_name=True`` so the models accept either the camelCase
wire format (Medium's API convention) or the snake_case Python name.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class MediumUser(BaseModel):
    """A Medium user (the authenticated user, returned by ``/me``)."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    id: str
    username: str = ""
    name: str = ""
    url: str = ""
    image_url: str = Field("", alias="imageUrl")


class MediumPublication(BaseModel):
    """A Medium publication the user is associated with."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    id: str
    name: str = ""
    description: str = ""
    url: str = ""
    image_url: str = Field("", alias="imageUrl")


class MediumPost(BaseModel):
    """A Medium post (article) returned by the publish endpoints."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    id: str
    title: str = ""
    author_id: str = Field("", alias="authorId")
    tags: list[str] = []
    url: str = ""
    canonical_url: str = Field("", alias="canonicalUrl")
    publish_status: str = Field("", alias="publishStatus")  # "public"|"draft"|"unlisted"
    published_at: Optional[int] = Field(None, alias="publishedAt")  # Unix epoch ms
    license: str = ""
    license_url: str = Field("", alias="licenseUrl")
