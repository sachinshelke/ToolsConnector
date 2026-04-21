"""Pydantic models for Okta connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Embedded models
# ---------------------------------------------------------------------------


class OktaProfile(BaseModel):
    """Okta user profile containing standard and custom attributes."""

    model_config = ConfigDict(frozen=True)

    first_name: Optional[str] = Field(None, alias="firstName")
    last_name: Optional[str] = Field(None, alias="lastName")
    email: Optional[str] = None
    login: Optional[str] = None
    mobile_phone: Optional[str] = Field(None, alias="mobilePhone")
    second_email: Optional[str] = Field(None, alias="secondEmail")
    display_name: Optional[str] = Field(None, alias="displayName")
    title: Optional[str] = None
    department: Optional[str] = None
    organization: Optional[str] = None
    extra: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class OktaUser(BaseModel):
    """An Okta user account."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    status: str = ""
    created: Optional[str] = None
    activated: Optional[str] = None
    last_login: Optional[str] = Field(None, alias="lastLogin")
    last_updated: Optional[str] = Field(None, alias="lastUpdated")
    status_changed: Optional[str] = Field(None, alias="statusChanged")
    profile: Optional[OktaProfile] = None
    credentials: Optional[dict[str, Any]] = None
    links: dict[str, Any] = Field(default_factory=dict, alias="_links")


class OktaGroup(BaseModel):
    """An Okta group."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    created: Optional[str] = None
    last_updated: Optional[str] = Field(None, alias="lastUpdated")
    last_membership_updated: Optional[str] = Field(None, alias="lastMembershipUpdated")
    type: str = ""
    name: str = ""
    description: str = ""
    profile: dict[str, Any] = Field(default_factory=dict)
    links: dict[str, Any] = Field(default_factory=dict, alias="_links")


class OktaApplication(BaseModel):
    """An Okta application integration."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    name: str = ""
    label: str = ""
    status: str = ""
    created: Optional[str] = None
    last_updated: Optional[str] = Field(None, alias="lastUpdated")
    sign_on_mode: Optional[str] = Field(None, alias="signOnMode")
    features: list[str] = Field(default_factory=list)
    visibility: dict[str, Any] = Field(default_factory=dict)
    links: dict[str, Any] = Field(default_factory=dict, alias="_links")


class OktaLogEvent(BaseModel):
    """An Okta system log event."""

    model_config = ConfigDict(frozen=True)

    uuid: str = ""
    published: Optional[str] = None
    event_type: Optional[str] = Field(None, alias="eventType")
    severity: Optional[str] = None
    display_message: Optional[str] = Field(None, alias="displayMessage")
    actor: Optional[dict[str, Any]] = None
    client: Optional[dict[str, Any]] = None
    outcome: Optional[dict[str, Any]] = None
    target: list[dict[str, Any]] = Field(default_factory=list)
    transaction: Optional[dict[str, Any]] = None
    debug_context: Optional[dict[str, Any]] = Field(None, alias="debugContext")
    authentication_context: Optional[dict[str, Any]] = Field(None, alias="authenticationContext")
