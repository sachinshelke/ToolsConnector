"""Pydantic models for Firebase Firestore connector types.

All response models use ``frozen=True`` to enforce immutability.

Firestore uses a special value encoding where each value is wrapped
in a type descriptor (e.g. ``{"stringValue": "hello"}``).  The helpers
in ``connector.py`` handle encoding/decoding transparently.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class FirestoreValue(BaseModel):
    """A decoded Firestore field value.

    Firestore REST API wraps values in type descriptors.  This model
    holds the decoded Python-native value after conversion.
    """

    model_config = ConfigDict(frozen=True)

    value: Any = None


class FirestoreDocument(BaseModel):
    """A single Firestore document.

    The ``fields`` dict maps field names to their Python-native values
    (already decoded from Firestore's type-descriptor format).
    """

    model_config = ConfigDict(frozen=True)

    name: Optional[str] = None
    document_id: Optional[str] = None
    fields: dict[str, Any] = Field(default_factory=dict)
    create_time: Optional[str] = None
    update_time: Optional[str] = None


class FirestoreQuery(BaseModel):
    """Parameters for a Firestore structured query.

    Used internally to construct the query request body.
    """

    model_config = ConfigDict(frozen=True)

    collection_id: str = ""
    where: Optional[list[dict[str, Any]]] = None
    order_by: Optional[list[dict[str, str]]] = None
    limit: Optional[int] = None


class FirestoreBatchWriteResult(BaseModel):
    """Result of a Firestore batch write operation."""

    model_config = ConfigDict(frozen=True)

    status: list[dict[str, Any]] = Field(default_factory=list)
    write_results: list[dict[str, Any]] = Field(default_factory=list)


class FirestoreCollection(BaseModel):
    """Metadata about a Firestore collection."""

    model_config = ConfigDict(frozen=True)

    collection_id: str = ""
