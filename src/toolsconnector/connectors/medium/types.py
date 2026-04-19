"""Pydantic models for Medium connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


class MediumUser(BaseModel):
    """A Medium user (the authenticated user, returned by ``/me``)."""

    model_config = ConfigDict(frozen=True)

    id: str
    username: str = ""
    name: str = ""
    url: str = ""
    imageUrl: str = ""


class MediumPublication(BaseModel):
    """A Medium publication the user is associated with."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str = ""
    description: str = ""
    url: str = ""
    imageUrl: str = ""


class MediumPost(BaseModel):
    """A Medium post (article) returned by the publish endpoints."""

    model_config = ConfigDict(frozen=True)

    id: str
    title: str = ""
    authorId: str = ""
    tags: list[str] = []
    url: str = ""
    canonicalUrl: str = ""
    publishStatus: str = ""  # "public" | "draft" | "unlisted"
    publishedAt: Optional[int] = None  # Unix epoch ms
    license: str = ""
    licenseUrl: str = ""
