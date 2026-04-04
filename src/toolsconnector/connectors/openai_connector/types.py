"""Pydantic models for OpenAI connector types.

All response models use ``frozen=True`` to enforce immutability.
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


class EmbeddingData(BaseModel):
    """A single embedding vector."""

    model_config = ConfigDict(frozen=True)

    index: int = 0
    embedding: list[float] = Field(default_factory=list)
    object: str = "embedding"


class Embedding(BaseModel):
    """Response from the embeddings endpoint."""

    model_config = ConfigDict(frozen=True)

    object: str = "list"
    data: list[EmbeddingData] = Field(default_factory=list)
    model: str = ""
    usage: Optional[Usage] = None


class ImageData(BaseModel):
    """A single generated image."""

    model_config = ConfigDict(frozen=True)

    url: Optional[str] = None
    b64_json: Optional[str] = None
    revised_prompt: Optional[str] = None


class ImageResult(BaseModel):
    """Response from the images generation endpoint."""

    model_config = ConfigDict(frozen=True)

    created: int = 0
    data: list[ImageData] = Field(default_factory=list)


class AudioTranscription(BaseModel):
    """Response from the audio transcription endpoint."""

    model_config = ConfigDict(frozen=True)

    text: str = ""
    language: Optional[str] = None
    duration: Optional[float] = None
    segments: Optional[list[dict[str, Any]]] = None


class ToolDefinition(BaseModel):
    """An assistant tool definition."""

    model_config = ConfigDict(frozen=True)

    type: str = "code_interpreter"


class Assistant(BaseModel):
    """An OpenAI Assistant."""

    model_config = ConfigDict(frozen=True)

    id: str
    object: str = "assistant"
    created_at: int = 0
    name: Optional[str] = None
    description: Optional[str] = None
    model: str = ""
    instructions: Optional[str] = None
    tools: list[ToolDefinition] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OpenAIFile(BaseModel):
    """An uploaded file in the OpenAI platform."""

    model_config = ConfigDict(frozen=True)

    id: str
    object: str = "file"
    bytes: int = 0
    created_at: int = 0
    filename: str = ""
    purpose: str = ""
    status: Optional[str] = None


class OpenAIModel(BaseModel):
    """An available OpenAI model."""

    model_config = ConfigDict(frozen=True)

    id: str
    object: str = "model"
    created: int = 0
    owned_by: str = ""
