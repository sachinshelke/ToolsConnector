"""Airtable connector -- records, bases, and schema operations."""

from __future__ import annotations

from .connector import Airtable
from .types import AirtableBase, AirtableField, AirtableRecord, AirtableTable, AirtableWebhook

__all__ = [
    "Airtable",
    "AirtableBase",
    "AirtableField",
    "AirtableRecord",
    "AirtableTable",
    "AirtableWebhook",
]
