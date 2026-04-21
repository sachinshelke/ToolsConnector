"""Pydantic models for Auth0 connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class Auth0User(BaseModel):
    """An Auth0 user account."""

    model_config = ConfigDict(frozen=True)

    user_id: str = ""
    email: str = ""
    email_verified: bool = False
    name: str = ""
    nickname: str = ""
    picture: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_login: Optional[str] = None
    last_ip: Optional[str] = None
    logins_count: int = 0
    blocked: bool = False
    identities: list[dict[str, Any]] = Field(default_factory=list)
    app_metadata: dict[str, Any] = Field(default_factory=dict)
    user_metadata: dict[str, Any] = Field(default_factory=dict)


class Auth0Connection(BaseModel):
    """An Auth0 connection (identity provider)."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    name: str = ""
    display_name: Optional[str] = None
    strategy: str = ""
    enabled_clients: list[str] = Field(default_factory=list)
    is_domain_connection: bool = False
    realms: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Auth0Role(BaseModel):
    """An Auth0 role."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    name: str = ""
    description: str = ""
