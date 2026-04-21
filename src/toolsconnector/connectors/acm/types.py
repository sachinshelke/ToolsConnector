"""Pydantic models for AWS ACM connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ACMCertificate(BaseModel):
    """Full ACM certificate details."""

    model_config = ConfigDict(frozen=True)

    certificate_arn: str = ""
    domain_name: str = ""
    status: str = ""
    type: str = ""
    issuer: str = ""
    created_at: Optional[str] = None
    not_before: Optional[str] = None
    not_after: Optional[str] = None
    serial: str = ""
    subject_alternative_names: list[str] = Field(default_factory=list)
    in_use_by: list[str] = Field(default_factory=list)


class ACMCertificateDetail(BaseModel):
    """Detailed ACM certificate information from DescribeCertificate."""

    model_config = ConfigDict(frozen=True)

    certificate_arn: str = ""
    domain_name: str = ""
    status: str = ""
    type: str = ""
    issuer: str = ""
    created_at: Optional[str] = None
    not_before: Optional[str] = None
    not_after: Optional[str] = None
    subject_alternative_names: list[str] = Field(default_factory=list)
    domain_validation_options: list[dict[str, Any]] = Field(default_factory=list)
    in_use_by: list[str] = Field(default_factory=list)
    renewal_eligibility: str = ""
    key_algorithm: str = ""
    failure_reason: str = ""


class ACMCertificateSummary(BaseModel):
    """Summary of an ACM certificate from ListCertificates."""

    model_config = ConfigDict(frozen=True)

    certificate_arn: str = ""
    domain_name: str = ""
    status: str = ""
    type: str = ""


class ACMTag(BaseModel):
    """A tag attached to an ACM certificate."""

    model_config = ConfigDict(frozen=True)

    key: str = ""
    value: str = ""
