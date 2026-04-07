"""Google Docs connector -- manage documents."""

from __future__ import annotations

from .connector import GoogleDocs
from .types import BatchUpdateResponse, Document

__all__ = [
    "GoogleDocs",
    "BatchUpdateResponse",
    "Document",
]
