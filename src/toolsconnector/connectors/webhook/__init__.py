"""Generic Webhook connector -- send HTTP requests to any endpoint."""

from __future__ import annotations

from .connector import Webhook
from .types import WebhookBatchResult, WebhookResponse

__all__ = [
    "Webhook",
    "WebhookBatchResult",
    "WebhookResponse",
]
