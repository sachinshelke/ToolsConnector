"""Pydantic models for LinkedIn connector types.

All response models use ``frozen=True`` to enforce immutability.

LinkedIn identifies entities by URNs (``urn:li:share:123``, ``urn:li:person:abc``).
We keep URNs as plain strings rather than parsing them into structured objects,
matching the Slack/Discord pattern of treating IDs as opaque strings.

LinkedIn post content can contain arbitrarily nested "content blocks" (articles,
images, polls, documents, carousels). Rather than modelling every shape, we
keep content-heavy fields as ``dict[str, Any]`` — same approach Slack takes for
``Message.attachments`` and ``Message.blocks``.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class LinkedInProfile(BaseModel):
    """The authenticated LinkedIn user's profile.

    Returned by the OIDC-compliant ``/v2/userinfo`` endpoint, which is the
    most reliable way to identify the authenticated user across API
    versions.
    """

    model_config = ConfigDict(frozen=True)

    sub: str  # OIDC subject (same as person URN suffix)
    name: str = ""
    given_name: str = ""
    family_name: str = ""
    email: Optional[str] = None
    email_verified: bool = False
    picture: Optional[str] = None
    locale: dict[str, Any] = Field(default_factory=dict)


class LinkedInPost(BaseModel):
    """A LinkedIn post (UGC share).

    The newer ``/rest/posts`` API returns posts identified by a
    ``urn:li:share:...`` or ``urn:li:ugcPost:...`` URN (``id`` field).
    Content blocks (articles, images, polls) live under ``content`` as a
    free-form dict.
    """

    model_config = ConfigDict(frozen=True)

    id: str  # Post URN
    author: str = ""  # Author URN (urn:li:person:... or urn:li:organization:...)
    commentary: str = ""
    visibility: str = ""  # "PUBLIC" | "CONNECTIONS" | "LOGGED_IN"
    lifecycleState: str = ""  # "PUBLISHED" | "DRAFT" | "PROCESSING"
    createdAt: Optional[int] = None  # Unix epoch ms
    publishedAt: Optional[int] = None  # Unix epoch ms
    content: dict[str, Any] = Field(default_factory=dict)
    distribution: dict[str, Any] = Field(default_factory=dict)


class LinkedInComment(BaseModel):
    """A comment on a LinkedIn post.

    Returned by the ``/v2/socialActions/{urn}/comments`` endpoint.
    """

    model_config = ConfigDict(frozen=True)

    id: str  # Comment URN
    actor: str = ""  # Commenter URN
    object: str = ""  # Parent post URN
    message: dict[str, Any] = Field(default_factory=dict)  # {"text": "..."}
    created: dict[str, Any] = Field(default_factory=dict)  # {"time": epoch_ms, "actor": urn}
    likesSummary: dict[str, Any] = Field(default_factory=dict)
