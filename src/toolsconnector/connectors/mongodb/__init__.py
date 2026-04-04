"""MongoDB Atlas Data API connector -- CRUD, aggregation, and count."""

from __future__ import annotations

from .connector import MongoDB
from .types import (
    MongoAggregateResult,
    MongoCountResult,
    MongoDeleteResult,
    MongoDocument,
    MongoInsertResult,
    MongoUpdateResult,
)

__all__ = [
    "MongoDB",
    "MongoAggregateResult",
    "MongoCountResult",
    "MongoDeleteResult",
    "MongoDocument",
    "MongoInsertResult",
    "MongoUpdateResult",
]
