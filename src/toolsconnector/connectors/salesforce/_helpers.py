"""Response parsers for the Salesforce connector."""

from __future__ import annotations

from typing import Any

from .types import (
    SalesforceLimits,
    SalesforceRecord,
    SObjectDescription,
    SObjectFieldInfo,
    SObjectInfo,
)


def parse_record(data: dict[str, Any]) -> SalesforceRecord:
    """Parse a raw Salesforce record JSON into a SalesforceRecord.

    Salesforce returns records as flat dicts with an ``attributes``
    key containing metadata.  We separate ``attributes`` and ``Id``
    from the remaining fields.

    Args:
        data: Raw JSON dict for a single record.

    Returns:
        A SalesforceRecord instance.
    """
    attributes = data.get("attributes", {})
    record_id = data.get("Id") or data.get("id")
    fields = {
        k: v
        for k, v in data.items()
        if k not in ("attributes", "Id", "id")
    }
    return SalesforceRecord(
        id=record_id,
        attributes=attributes,
        fields=fields,
    )


def parse_sobject_info(data: dict[str, Any]) -> SObjectInfo:
    """Parse a compact sObject description from the global describe."""
    return SObjectInfo(
        name=data.get("name", ""),
        label=data.get("label", ""),
        label_plural=data.get("labelPlural"),
        key_prefix=data.get("keyPrefix"),
        queryable=data.get("queryable", False),
        searchable=data.get("searchable", False),
        createable=data.get("createable", False),
        updateable=data.get("updateable", False),
        deletable=data.get("deletable", False),
        custom=data.get("custom", False),
        urls=data.get("urls", {}),
    )


def parse_field_info(data: dict[str, Any]) -> SObjectFieldInfo:
    """Parse a single field description."""
    return SObjectFieldInfo(
        name=data.get("name", ""),
        label=data.get("label", ""),
        type=data.get("type", ""),
        length=data.get("length"),
        nillable=data.get("nillable", False),
        updateable=data.get("updateable", False),
        createable=data.get("createable", False),
        custom=data.get("custom", False),
    )


def parse_describe(data: dict[str, Any]) -> SObjectDescription:
    """Parse a full sObject describe response."""
    fields = [parse_field_info(f) for f in data.get("fields", [])]
    return SObjectDescription(
        name=data.get("name", ""),
        label=data.get("label", ""),
        label_plural=data.get("labelPlural"),
        key_prefix=data.get("keyPrefix"),
        queryable=data.get("queryable", False),
        searchable=data.get("searchable", False),
        createable=data.get("createable", False),
        updateable=data.get("updateable", False),
        deletable=data.get("deletable", False),
        custom=data.get("custom", False),
        fields=fields,
        record_type_infos=data.get("recordTypeInfos", []),
    )


def parse_limits(data: dict[str, Any]) -> SalesforceLimits:
    """Parse the /limits response into a SalesforceLimits model."""

    def _extract(key: str) -> dict[str, int]:
        entry = data.get(key, {})
        return {
            "Max": entry.get("Max", 0),
            "Remaining": entry.get("Remaining", 0),
        }

    return SalesforceLimits(
        daily_api_requests=_extract("DailyApiRequests"),
        daily_bulk_api_requests=_extract("DailyBulkApiRequests"),
        daily_streaming_api_events=_extract("DailyStreamingApiEvents"),
        data_storage_mb=_extract("DataStorageMB"),
        file_storage_mb=_extract("FileStorageMB"),
        single_email=_extract("SingleEmail"),
        mass_email=_extract("MassEmail"),
        hourly_time_based_workflow=_extract("HourlyTimeBasedWorkflow"),
        raw=data,
    )
