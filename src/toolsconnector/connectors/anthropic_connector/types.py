"""Pydantic models for Anthropic connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Shared / embedded models
# ---------------------------------------------------------------------------


class ContentBlock(BaseModel):
    """A single content block in an Anthropic message.

    Can represent text, tool use, or tool result content.
    """

    model_config = ConfigDict(frozen=True)

    type: str = "text"
    text: Optional[str] = None
    id: Optional[str] = None
    name: Optional[str] = None
    input: Optional[dict[str, Any]] = None
    tool_use_id: Optional[str] = None
    content: Optional[str] = None


class Usage(BaseModel):
    """Token usage statistics for an Anthropic API call."""

    model_config = ConfigDict(frozen=True)

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: Optional[int] = None
    cache_read_input_tokens: Optional[int] = None


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class AnthropicMessage(BaseModel):
    """Response from the Anthropic messages endpoint."""

    model_config = ConfigDict(frozen=True)

    id: str
    type: str = "message"
    role: str = "assistant"
    content: list[ContentBlock] = Field(default_factory=list)
    model: str = ""
    stop_reason: Optional[str] = None
    stop_sequence: Optional[str] = None
    usage: Optional[Usage] = None


class TokenCount(BaseModel):
    """Response from the token counting endpoint."""

    model_config = ConfigDict(frozen=True)

    input_tokens: int = 0


class AnthropicModel(BaseModel):
    """An available Anthropic model."""

    model_config = ConfigDict(frozen=True)

    id: str
    display_name: str = ""
    type: str = "model"
    created_at: Optional[str] = None


class AnthropicBatch(BaseModel):
    """A Message Batch from the Anthropic API."""

    model_config = ConfigDict(frozen=True)

    id: str
    type: str = "message_batch"
    processing_status: Optional[str] = None
    request_counts: Optional[dict[str, int]] = None
    ended_at: Optional[str] = None
    created_at: Optional[str] = None
    expires_at: Optional[str] = None
