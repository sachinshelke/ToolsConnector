"""Pydantic models for Salesforce connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Top-level response models
# ---------------------------------------------------------------------------


class SalesforceRecord(BaseModel):
    """A generic Salesforce sObject record.

    The ``attributes`` dict typically contains ``type`` (sObject name)
    and ``url`` (record detail URL).  All other fields are stored in
    ``fields`` as a flat key-value dict.
    """

    model_config = ConfigDict(frozen=True)

    id: Optional[str] = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    fields: dict[str, Any] = Field(default_factory=dict)

    @property
    def sobject_type(self) -> Optional[str]:
        """Shortcut to the sObject type from attributes."""
        return self.attributes.get("type")


class SalesforceRecordId(BaseModel):
    """Minimal response from a record creation containing only the ID."""

    model_config = ConfigDict(frozen=True)

    id: str
    success: bool = True
    errors: list[Any] = Field(default_factory=list)


class SObjectFieldInfo(BaseModel):
    """Describes a single field on a Salesforce sObject."""

    model_config = ConfigDict(frozen=True)

    name: str = ""
    label: str = ""
    type: str = ""
    length: Optional[int] = None
    nillable: bool = False
    updateable: bool = False
    createable: bool = False
    custom: bool = False


class SObjectDescription(BaseModel):
    """Full metadata description of a Salesforce sObject."""

    model_config = ConfigDict(frozen=True)

    name: str = ""
    label: str = ""
    label_plural: Optional[str] = None
    key_prefix: Optional[str] = None
    queryable: bool = False
    searchable: bool = False
    createable: bool = False
    updateable: bool = False
    deletable: bool = False
    custom: bool = False
    fields: list[SObjectFieldInfo] = Field(default_factory=list)
    record_type_infos: list[dict[str, Any]] = Field(default_factory=list)


class SObjectInfo(BaseModel):
    """Compact sObject metadata returned by the global describe endpoint."""

    model_config = ConfigDict(frozen=True)

    name: str = ""
    label: str = ""
    label_plural: Optional[str] = None
    key_prefix: Optional[str] = None
    queryable: bool = False
    searchable: bool = False
    createable: bool = False
    updateable: bool = False
    deletable: bool = False
    custom: bool = False
    urls: dict[str, str] = Field(default_factory=dict)


class SalesforceLimits(BaseModel):
    """Salesforce org API usage limits and remaining counts.

    Each limit is represented as a dict with ``Max`` and ``Remaining``
    keys, matching the structure returned by the ``/limits`` endpoint.
    """

    model_config = ConfigDict(frozen=True)

    daily_api_requests: dict[str, int] = Field(default_factory=dict)
    daily_bulk_api_requests: dict[str, int] = Field(default_factory=dict)
    daily_streaming_api_events: dict[str, int] = Field(default_factory=dict)
    data_storage_mb: dict[str, int] = Field(default_factory=dict)
    file_storage_mb: dict[str, int] = Field(default_factory=dict)
    single_email: dict[str, int] = Field(default_factory=dict)
    mass_email: dict[str, int] = Field(default_factory=dict)
    hourly_time_based_workflow: dict[str, int] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)
