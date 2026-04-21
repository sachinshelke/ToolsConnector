"""Pydantic models for Generic Webhook connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class WebhookResponse(BaseModel):
    """Response from a webhook delivery attempt."""

    model_config = ConfigDict(frozen=True)

    url: str
    method: str = "POST"
    status_code: int = 0
    success: bool = False
    response_body: Optional[str] = None
    response_headers: dict[str, str] = Field(default_factory=dict)
    elapsed_ms: float = 0.0
    error: Optional[str] = None


class WebhookBatchResult(BaseModel):
    """Result of a batch webhook delivery."""

    model_config = ConfigDict(frozen=True)

    total: int = 0
    succeeded: int = 0
    failed: int = 0
    results: list[WebhookResponse] = Field(default_factory=list)

    @property
    def all_succeeded(self) -> bool:
        """Check if all deliveries succeeded."""
        return self.failed == 0 and self.total > 0
