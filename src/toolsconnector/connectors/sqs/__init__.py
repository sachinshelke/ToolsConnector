"""AWS SQS connector -- send, receive, and manage messages in SQS queues."""

from __future__ import annotations

from .connector import SQS
from .types import (
    SQSBatchResult,
    SQSBatchResultEntry,
    SQSMessage,
    SQSQueue,
    SQSQueueAttributes,
    SQSSendResult,
)

__all__ = [
    "SQS",
    "SQSBatchResult",
    "SQSBatchResultEntry",
    "SQSMessage",
    "SQSQueue",
    "SQSQueueAttributes",
    "SQSSendResult",
]
