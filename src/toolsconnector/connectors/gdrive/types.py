"""Pydantic models for Google Drive connector types.

All response models use ``frozen=True`` to enforce immutability.
Input-only models (used as parameters) are left mutable.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class DriveUser(BaseModel):
    """A Google Drive user reference."""

    model_config = ConfigDict(frozen=True)

    display_name: str = ""
    email_address: Optional[str] = None
    photo_link: Optional[str] = None


class DriveFile(BaseModel):
    """A file or folder in Google Drive."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    mime_type: str = ""
    description: Optional[str] = None
    starred: bool = False
    trashed: bool = False
    size: Optional[int] = None
    created_time: Optional[str] = None
    modified_time: Optional[str] = None
    parents: list[str] = Field(default_factory=list)
    web_view_link: Optional[str] = None
    web_content_link: Optional[str] = None
    icon_link: Optional[str] = None
    owners: list[DriveUser] = Field(default_factory=list)
    shared: bool = False


class FilePermission(BaseModel):
    """A permission entry on a Drive file."""

    model_config = ConfigDict(frozen=True)

    id: str
    type: str  # "user", "group", "domain", "anyone"
    role: str  # "owner", "organizer", "writer", "commenter", "reader"
    email_address: Optional[str] = None
    display_name: Optional[str] = None
    domain: Optional[str] = None


class FolderId(BaseModel):
    """Result of creating a folder."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    web_view_link: Optional[str] = None


class FileUploadResult(BaseModel):
    """Result of uploading a file."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    mime_type: str = ""
    size: Optional[int] = None
    web_view_link: Optional[str] = None


class FileDownloadResult(BaseModel):
    """Result of downloading a file (metadata + raw bytes)."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    mime_type: str = ""
    size: int = 0
    content_base64: str = ""


class StorageQuota(BaseModel):
    """Google Drive storage quota information."""

    model_config = ConfigDict(frozen=True)

    limit: Optional[str] = None
    usage: Optional[str] = None
    usage_in_drive: Optional[str] = None
    usage_in_drive_trash: Optional[str] = None
