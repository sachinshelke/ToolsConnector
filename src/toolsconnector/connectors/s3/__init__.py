"""AWS S3 connector — buckets, objects, and metadata operations."""

from __future__ import annotations

from .connector import S3
from .types import (
    S3Bucket,
    S3BucketPolicy,
    S3CopyResult,
    S3Object,
    S3ObjectData,
    S3ObjectMetadata,
    S3ObjectVersion,
    S3PresignedUrl,
    S3PutResult,
)

__all__ = [
    "S3",
    "S3Bucket",
    "S3BucketPolicy",
    "S3CopyResult",
    "S3Object",
    "S3ObjectData",
    "S3ObjectMetadata",
    "S3ObjectVersion",
    "S3PresignedUrl",
    "S3PutResult",
]
