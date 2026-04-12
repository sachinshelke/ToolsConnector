"""Pinecone connector -- vector database operations and index management."""

from __future__ import annotations

from .connector import Pinecone
from .types import (
    PineconeCollection,
    PineconeIndex,
    PineconeMatch,
    PineconeQueryResult,
    PineconeStats,
    PineconeVector,
)

__all__ = [
    "Pinecone",
    "PineconeCollection",
    "PineconeIndex",
    "PineconeMatch",
    "PineconeQueryResult",
    "PineconeStats",
    "PineconeVector",
]
