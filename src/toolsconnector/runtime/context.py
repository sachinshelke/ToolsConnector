"""Action execution context."""

from __future__ import annotations

import uuid
from typing import Any, Optional

from pydantic import BaseModel, Field


class ActionContext(BaseModel):
    """Context for the current action invocation.

    Passed through the middleware pipeline so each middleware
    can read/modify execution metadata.

    Attributes:
        connector_name: Name of the connector (e.g., 'gmail').
        action_name: Name of the action being executed (e.g., 'list_emails').
        args: Positional arguments passed to the action.
        kwargs: Keyword arguments passed to the action.
        tenant_id: Tenant identifier for multi-tenant deployments.
        request_id: Unique ID for this invocation (for tracing/logging).
        attempt: Current retry attempt number (1-based).
        metadata: Arbitrary key-value metadata for custom middleware.
    """

    connector_name: str
    action_name: str
    args: dict[str, Any] = Field(default_factory=dict)
    kwargs: dict[str, Any] = Field(default_factory=dict)
    tenant_id: Optional[str] = None
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    attempt: int = 1
    metadata: dict[str, Any] = Field(default_factory=dict)
