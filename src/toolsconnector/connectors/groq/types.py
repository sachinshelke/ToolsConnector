"""Pydantic models for the Groq connector types.

Groq exposes an OpenAI-compatible REST API, so these models mirror the
shapes returned by the chat-completions, models, audio, files, and batch
endpoints. All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Shared / embedded models
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    """A single message in a chat conversation."""

    model_config = ConfigDict(frozen=True)

    role: str
    content: Optional[str] = None
    name: Optional[str] = None
    tool_calls: Optional[list[dict[str, Any]]] = None
    tool_call_id: Optional[str] = None


class Usage(BaseModel):
    """Token usage statistics for an API call."""

    model_config = ConfigDict(frozen=True)

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ChatChoice(BaseModel):
    """A single completion choice from a chat completion response."""

    model_config = ConfigDict(frozen=True)

    index: int = 0
    message: ChatMessage
    finish_reason: Optional[str] = None


class ChatCompletion(BaseModel):
    """Response from the chat completions endpoint."""

    model_config = ConfigDict(frozen=True)

    id: str
    object: str = "chat.completion"
    created: int = 0
    model: str = ""
    choices: list[ChatChoice] = Field(default_factory=list)
    usage: Optional[Usage] = None
    system_fingerprint: Optional[str] = None


class GroqModel(BaseModel):
    """An available Groq model."""

    model_config = ConfigDict(frozen=True)

    id: str
    object: str = "model"
    created: int = 0
    owned_by: str = ""
    active: Optional[bool] = None
    context_window: Optional[int] = None


class AudioTranscription(BaseModel):
    """Response from the audio transcription or translation endpoints."""

    model_config = ConfigDict(frozen=True)

    text: str = ""
    language: Optional[str] = None
    duration: Optional[float] = None
    segments: Optional[list[dict[str, Any]]] = None


# ---------------------------------------------------------------------------
# Files API models
# ---------------------------------------------------------------------------


class GroqFile(BaseModel):
    """A file uploaded to Groq (e.g. JSONL batch input)."""

    model_config = ConfigDict(frozen=True)

    id: str
    object: str = "file"
    bytes: int = 0
    created_at: int = 0
    filename: str = ""
    purpose: str = ""


# ---------------------------------------------------------------------------
# Batch API models
# ---------------------------------------------------------------------------


class BatchRequestCounts(BaseModel):
    """Per-batch tally of total / completed / failed requests."""

    model_config = ConfigDict(frozen=True)

    total: int = 0
    completed: int = 0
    failed: int = 0


class Batch(BaseModel):
    """A batch job processing many requests asynchronously.

    Mirrors the OpenAI-compatible batch object returned by Groq's
    ``/batches`` endpoints, including the lifecycle timestamps and the
    input/output/error file references needed to retrieve results.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    object: str = "batch"
    endpoint: str = ""
    input_file_id: str = ""
    completion_window: str = ""
    status: str = ""
    output_file_id: Optional[str] = None
    error_file_id: Optional[str] = None
    errors: Optional[dict[str, Any]] = None
    request_counts: Optional[BatchRequestCounts] = None
    created_at: int = 0
    in_progress_at: Optional[int] = None
    expires_at: Optional[int] = None
    finalizing_at: Optional[int] = None
    completed_at: Optional[int] = None
    failed_at: Optional[int] = None
    expired_at: Optional[int] = None
    cancelling_at: Optional[int] = None
    cancelled_at: Optional[int] = None
    metadata: Optional[dict[str, Any]] = None
