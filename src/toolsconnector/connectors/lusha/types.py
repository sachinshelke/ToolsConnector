"""Pydantic models for the Lusha connector (V3 API).

Lusha's V3 reveal flow is two-step: a *search* returns a non-PII preview
(profile + ``id`` + ``canReveal``), and an *enrich* call reveals the actual
emails and phones. Contact identity fields are typed here; the sprawling,
fast-moving firmographic surface on companies is kept as ``dict`` (same
approach Slack/LinkedIn take for deeply-nested vendor payloads).

Every contact/company call also reports real spend in ``billing.creditsCharged``
— the connector surfaces that on the result envelope so callers can track cost,
since Lusha bills per revealed datapoint (email = 1, phone = 5).

Models use ``extra="ignore"`` + ``populate_by_name`` so they accept Lusha's
camelCase wire format and drop unmodeled fields rather than raising.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

_CFG = ConfigDict(frozen=True, populate_by_name=True, extra="ignore")


class LushaEmail(BaseModel):
    """A revealed email address."""

    model_config = _CFG

    email: str
    type: str = ""  # "work" | "private" | "unknown"
    confidence: Optional[str] = None  # e.g. "A+"
    update_date: Optional[str] = Field(None, alias="updateDate")


class LushaPhone(BaseModel):
    """A revealed phone number. ``do_not_call`` is Lusha's DNC flag — honor it."""

    model_config = _CFG

    number: str  # E.164-ish, e.g. "+14155551234"
    type: str = ""  # "mobile" | "direct" | "work" | "unknown"
    do_not_call: bool = Field(False, alias="doNotCall")
    update_date: Optional[str] = Field(None, alias="updateDate")


class LushaContact(BaseModel):
    """A Lusha contact — a preview (no emails/phones) or fully enriched.

    After a *search* call, ``emails``/``phones`` are empty and ``can_reveal``
    lists what an *enrich* would return (with its credit cost). After *enrich*
    (or *search-and-enrich*), ``emails`` and ``phones`` are populated.
    """

    model_config = _CFG

    id: str = ""
    full_name: str = Field("", alias="fullName")
    first_name: str = Field("", alias="firstName")
    last_name: str = Field("", alias="lastName")
    job_title: dict[str, Any] = Field(default_factory=dict, alias="jobTitle")
    company: dict[str, Any] = Field(default_factory=dict)
    location: dict[str, Any] = Field(default_factory=dict)  # incl. isEuContact
    social_links: dict[str, Any] = Field(default_factory=dict, alias="socialLinks")
    emails: list[LushaEmail] = Field(default_factory=list)
    phones: list[LushaPhone] = Field(default_factory=list)
    has: list[str] = Field(default_factory=list)  # available data points, e.g. "emails"
    can_reveal: list[dict[str, Any]] = Field(default_factory=list, alias="canReveal")
    client_reference_id: Optional[str] = Field(None, alias="clientReferenceId")


class LushaCompany(BaseModel):
    """A Lusha company (firmographics). Common fields typed; the long tail is raw."""

    model_config = _CFG

    id: str = ""
    name: str = ""
    domain: str = ""
    description: str = ""
    employee_count: dict[str, Any] = Field(default_factory=dict, alias="employeeCount")
    industry: str = ""
    location: dict[str, Any] = Field(default_factory=dict)
    social_links: dict[str, Any] = Field(default_factory=dict, alias="socialLinks")
    logo_url: Optional[str] = Field(None, alias="logoUrl")


class LushaContactResult(BaseModel):
    """Envelope for contact calls — the people plus the credit spend."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    request_id: str = ""
    contacts: list[LushaContact] = Field(default_factory=list)
    credits_charged: int = 0


class LushaCompanyResult(BaseModel):
    """Envelope for company calls — firmographics plus credit spend."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    request_id: str = ""
    companies: list[LushaCompany] = Field(default_factory=list)
    credits_charged: int = 0
