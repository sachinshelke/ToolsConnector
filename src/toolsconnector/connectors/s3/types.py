"""Pydantic models for AWS S3 connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class S3Bucket(BaseModel):
    """An S3 bucket."""

    model_config = ConfigDict(frozen=True)

    name: str
    creation_date: Optional[str] = None
    region: Optional[str] = None


class S3Object(BaseModel):
    """An S3 object (key) within a bucket."""

    model_config = ConfigDict(frozen=True)

    key: str
    size: int = 0
    last_modified: Optional[str] = None
    etag: Optional[str] = None
    storage_class: Optional[str] = None


class S3ObjectMetadata(BaseModel):
    """Metadata for an S3 object (from HEAD request)."""

    model_config = ConfigDict(frozen=True)

    key: str
    content_type: Optional[str] = None
    content_length: int = 0
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    metadata: dict[str, str] = Field(default_factory=dict)
    storage_class: Optional[str] = None
    version_id: Optional[str] = None


class S3ObjectData(BaseModel):
    """S3 object content and metadata (from GET request).

    The ``body`` field contains the raw bytes of the object. For text
    content, decode using the appropriate charset from ``content_type``.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    key: str
    body: bytes = b""
    content_type: Optional[str] = None
    content_length: int = 0
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    metadata: dict[str, str] = Field(default_factory=dict)


class S3PutResult(BaseModel):
    """Result of a PUT object operation."""

    model_config = ConfigDict(frozen=True)

    key: str
    etag: Optional[str] = None
    version_id: Optional[str] = None


class S3CopyResult(BaseModel):
    """Result of a COPY object operation."""

    model_config = ConfigDict(frozen=True)

    source_key: str
    dest_key: str
    etag: Optional[str] = None
    last_modified: Optional[str] = None
