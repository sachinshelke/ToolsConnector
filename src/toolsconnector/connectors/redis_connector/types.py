"""Pydantic models for Redis (Upstash) connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class RedisResult(BaseModel):
    """Generic result from a Redis command.

    The ``result`` field contains the command return value, which may
    be a string, integer, list, or ``None`` depending on the command.
    """

    model_config = ConfigDict(frozen=True)

    result: Any = None


class RedisKeyInfo(BaseModel):
    """Information about a Redis key."""

    model_config = ConfigDict(frozen=True)

    key: str = ""
    type: Optional[str] = None
    ttl: Optional[int] = None
