"""Pydantic models for MongoDB Atlas Data API connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class MongoDocument(BaseModel):
    """A single MongoDB document.

    The ``document`` field contains the full document dict, including
    the ``_id`` field.
    """

    model_config = ConfigDict(frozen=True)

    document: dict[str, Any] = Field(default_factory=dict)


class MongoInsertResult(BaseModel):
    """Result of an insert operation."""

    model_config = ConfigDict(frozen=True)

    inserted_id: Optional[str] = None
    inserted_ids: list[str] = Field(default_factory=list)


class MongoUpdateResult(BaseModel):
    """Result of an update operation."""

    model_config = ConfigDict(frozen=True)

    matched_count: int = 0
    modified_count: int = 0
    upserted_id: Optional[str] = None


class MongoDeleteResult(BaseModel):
    """Result of a delete operation."""

    model_config = ConfigDict(frozen=True)

    deleted_count: int = 0


class MongoAggregateResult(BaseModel):
    """Result of an aggregation pipeline execution."""

    model_config = ConfigDict(frozen=True)

    documents: list[dict[str, Any]] = Field(default_factory=list)


class MongoCountResult(BaseModel):
    """Result of a count operation."""

    model_config = ConfigDict(frozen=True)

    count: int = 0
