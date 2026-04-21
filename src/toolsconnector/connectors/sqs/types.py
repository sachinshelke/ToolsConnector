"""Pydantic models for AWS SQS connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class SQSMessage(BaseModel):
    """An SQS message received from a queue."""

    model_config = ConfigDict(frozen=True)

    message_id: str = ""
    receipt_handle: str = ""
    body: str = ""
    md5_of_body: str = ""
    attributes: dict[str, str] = Field(default_factory=dict)
    message_attributes: dict[str, Any] = Field(default_factory=dict)


class SQSQueue(BaseModel):
    """An SQS queue reference."""

    model_config = ConfigDict(frozen=True)

    queue_url: str = ""


class SQSQueueAttributes(BaseModel):
    """Attributes of an SQS queue."""

    model_config = ConfigDict(frozen=True)

    queue_arn: str = ""
    approximate_number_of_messages: int = 0
    approximate_number_of_messages_not_visible: int = 0
    approximate_number_of_messages_delayed: int = 0
    created_timestamp: str = ""
    last_modified_timestamp: str = ""
    visibility_timeout: str = ""
    maximum_message_size: str = ""
    message_retention_period: str = ""
    delay_seconds: str = ""
    receive_message_wait_time_seconds: str = ""
    raw_attributes: dict[str, str] = Field(default_factory=dict)


class SQSSendResult(BaseModel):
    """Result of sending a message to SQS."""

    model_config = ConfigDict(frozen=True)

    message_id: str = ""
    md5_of_message_body: str = ""
    sequence_number: Optional[str] = None


class SQSBatchResultEntry(BaseModel):
    """Result of a single entry in a batch send."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    message_id: str = ""
    md5_of_message_body: str = ""


class SQSBatchResult(BaseModel):
    """Result of a batch send operation."""

    model_config = ConfigDict(frozen=True)

    successful: list[SQSBatchResultEntry] = Field(default_factory=list)
    failed: list[dict[str, Any]] = Field(default_factory=list)
