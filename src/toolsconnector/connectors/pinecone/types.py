"""Pydantic models for Pinecone connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Input / shared models
# ---------------------------------------------------------------------------


class PineconeVector(BaseModel):
    """A vector to upsert into a Pinecone index."""

    model_config = ConfigDict(frozen=True)

    id: str
    values: list[float] = Field(default_factory=list)
    metadata: Optional[dict[str, Any]] = None
    sparse_values: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class PineconeMatch(BaseModel):
    """A single match result from a vector query."""

    model_config = ConfigDict(frozen=True)

    id: str
    score: float = 0.0
    values: list[float] = Field(default_factory=list)
    metadata: Optional[dict[str, Any]] = None
    sparse_values: Optional[dict[str, Any]] = None


class PineconeQueryResult(BaseModel):
    """Response from a vector query operation."""

    model_config = ConfigDict(frozen=True)

    namespace: str = ""
    matches: list[PineconeMatch] = Field(default_factory=list)
    usage: Optional[dict[str, int]] = None


class PineconeUpsertResult(BaseModel):
    """Response from a vector upsert operation."""

    model_config = ConfigDict(frozen=True)

    upserted_count: int = 0


class PineconeFetchResult(BaseModel):
    """Response from a vector fetch operation."""

    model_config = ConfigDict(frozen=True)

    namespace: str = ""
    vectors: dict[str, PineconeVector] = Field(default_factory=dict)
    usage: Optional[dict[str, int]] = None


class NamespaceStats(BaseModel):
    """Statistics for a single namespace within an index."""

    model_config = ConfigDict(frozen=True)

    vector_count: int = 0


class PineconeStats(BaseModel):
    """Statistics for a Pinecone index."""

    model_config = ConfigDict(frozen=True)

    dimension: int = 0
    index_fullness: float = 0.0
    total_vector_count: int = 0
    namespaces: dict[str, NamespaceStats] = Field(default_factory=dict)


class PineconeVectorListItem(BaseModel):
    """A vector ID returned from the list vectors endpoint."""

    model_config = ConfigDict(frozen=True)

    id: str


class PineconeVectorList(BaseModel):
    """Response from listing vectors."""

    model_config = ConfigDict(frozen=True)

    vectors: list[PineconeVectorListItem] = Field(default_factory=list)
    namespace: str = ""
    next_pagination_token: Optional[str] = None


class PineconeIndex(BaseModel):
    """A Pinecone index from the control plane."""

    model_config = ConfigDict(frozen=True)

    name: str
    dimension: int = 0
    metric: str = "cosine"
    host: str = ""
    status: Optional[dict[str, Any]] = None
    spec: Optional[dict[str, Any]] = None


class DeleteResult(BaseModel):
    """Response from a delete operation (empty on success)."""

    model_config = ConfigDict(frozen=True)

    deleted: bool = True
