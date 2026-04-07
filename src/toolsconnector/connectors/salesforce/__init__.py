"""Salesforce connector -- SOQL, SOSL, and sObject management."""

from __future__ import annotations

from .connector import Salesforce
from .types import (
    SalesforceLimits,
    SalesforceRecord,
    SalesforceRecordId,
    SObjectDescription,
    SObjectFieldInfo,
    SObjectInfo,
)

__all__ = [
    "Salesforce",
    "SalesforceLimits",
    "SalesforceRecord",
    "SalesforceRecordId",
    "SObjectDescription",
    "SObjectFieldInfo",
    "SObjectInfo",
]
