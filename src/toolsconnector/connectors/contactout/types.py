"""Pydantic models for the ContactOut connector.

ContactOut's endpoints return contact data under **inconsistent field names**
— search/v2-batch use plural arrays (``work_emails``/``personal_emails``/
``phones``), the LinkedIn-enrich/lookup endpoints use ``work_email[]`` /
``personal_email[]`` / ``phone[]``, and ``/email/enrich`` uses camelCase
singulars (``workEmail`` / ``workEmailStatus``). The connector normalizes all
of them into the single canonical :class:`ContactOutProfile` shape below, so
callers always read ``work_emails`` / ``personal_emails`` / ``phones`` as lists.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ContactOutProfile(BaseModel):
    """A person record, normalized to one canonical shape across all endpoints."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    linkedin_url: str = ""
    full_name: str = ""
    headline: str = ""
    title: str = ""
    company: Any = ""  # ContactOut returns this as a name string or an object
    location: str = ""
    emails: list[str] = Field(default_factory=list)  # all known emails
    work_emails: list[str] = Field(default_factory=list)
    personal_emails: list[str] = Field(default_factory=list)
    phones: list[str] = Field(default_factory=list)
    work_email_status: dict[str, Any] = Field(default_factory=dict)  # {email: Verified|Unverified}
    github: list[str] = Field(default_factory=list)
    experience: list[dict[str, Any]] = Field(default_factory=list)
    education: list[dict[str, Any]] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
