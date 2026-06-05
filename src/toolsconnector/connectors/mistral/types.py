"""Pydantic models for the Mistral connector types.

All response models use ``frozen=True`` to enforce immutability. Mistral's
core inference REST API (chat, FIM, embeddings) is OpenAI-compatible, so
those models intentionally mirror the shapes returned by
``api.mistral.ai/v1``. The platform-management surface (files, fine-tuning
jobs, batch jobs, models, OCR, classifiers) follows Mistral's own schemas
as documented at https://docs.mistral.ai/api/ .
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
# Chat / FIM / agents completion models
# ---------------------------------------------------------------------------


class ChatChoice(BaseModel):
    """A single completion choice from a chat or FIM completion response."""

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


class FIMCompletion(BaseModel):
    """Response from the fill-in-the-middle (FIM) completions endpoint."""

    model_config = ConfigDict(frozen=True)

    id: str
    object: str = "chat.completion"
    created: int = 0
    model: str = ""
    choices: list[ChatChoice] = Field(default_factory=list)
    usage: Optional[Usage] = None


class AgentsCompletion(BaseModel):
    """Response from the agents completions endpoint (``/agents/completions``)."""

    model_config = ConfigDict(frozen=True)

    id: str
    object: str = "chat.completion"
    created: int = 0
    model: str = ""
    choices: list[ChatChoice] = Field(default_factory=list)
    usage: Optional[Usage] = None


# ---------------------------------------------------------------------------
# Embedding models
# ---------------------------------------------------------------------------


class EmbeddingData(BaseModel):
    """A single embedding vector."""

    model_config = ConfigDict(frozen=True)

    index: int = 0
    embedding: list[float] = Field(default_factory=list)
    object: str = "embedding"


class Embedding(BaseModel):
    """Response from the embeddings endpoint."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    object: str = "list"
    data: list[EmbeddingData] = Field(default_factory=list)
    model: str = ""
    usage: Optional[Usage] = None


# ---------------------------------------------------------------------------
# Model listing / management
# ---------------------------------------------------------------------------


class MistralModel(BaseModel):
    """An available Mistral model card.

    Covers both base and fine-tuned model cards returned by
    ``GET /models`` and ``GET /models/{model_id}``. Fine-tuned cards add
    ``root``/``archived`` metadata that base cards omit.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    object: str = "model"
    created: int = 0
    owned_by: str = ""
    name: Optional[str] = None
    description: Optional[str] = None
    max_context_length: Optional[int] = None
    aliases: list[str] = Field(default_factory=list)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    type: Optional[str] = None
    root: Optional[str] = None
    archived: Optional[bool] = None


class ModelDeleted(BaseModel):
    """Result of deleting a fine-tuned model (``DELETE /models/{id}``)."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    object: str = "model"
    deleted: bool = False


class ArchiveModelResult(BaseModel):
    """Result of (un)archiving a fine-tuned model.

    Returned by ``POST``/``DELETE /fine_tuning/models/{id}/archive``.
    """

    model_config = ConfigDict(frozen=True)

    id: str = ""
    object: str = "model"
    archived: bool = False


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------


class MistralFile(BaseModel):
    """A file uploaded to the Mistral platform.

    Mirrors Mistral's ``FileSchema``. Note Mistral reports size under
    ``size_bytes`` (not ``bytes``) and exposes ``sample_type``/``source``
    metadata used by the fine-tuning pipeline.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    object: str = "file"
    size_bytes: int = 0
    created_at: int = 0
    filename: str = ""
    purpose: str = ""
    sample_type: Optional[str] = None
    num_lines: Optional[int] = None
    mimetype: Optional[str] = None
    source: Optional[str] = None


class FileDeleted(BaseModel):
    """Result of deleting a file (``DELETE /files/{file_id}``)."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    object: str = "file"
    deleted: bool = False


class FileSignedURL(BaseModel):
    """A temporary signed download URL for a file (``GET /files/{id}/url``)."""

    model_config = ConfigDict(frozen=True)

    url: str = ""


# ---------------------------------------------------------------------------
# Fine-tuning jobs
# ---------------------------------------------------------------------------


class FineTuningJob(BaseModel):
    """A Mistral fine-tuning job.

    Covers the ``CompletionFineTuningJobDetails`` / ``ClassifierFineTuning
    JobDetails`` shapes returned by the ``/fine_tuning/jobs`` endpoints.
    Mistral uses ``training_files``/``validation_files`` (lists of file
    IDs) rather than a single ``training_file``.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    object: str = "job"
    model: str = ""
    status: Optional[str] = None
    job_type: Optional[str] = None
    created_at: int = 0
    modified_at: int = 0
    training_files: list[str] = Field(default_factory=list)
    validation_files: list[str] = Field(default_factory=list)
    fine_tuned_model: Optional[str] = None
    suffix: Optional[str] = None
    auto_start: Optional[bool] = None
    trained_tokens: Optional[int] = None
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    integrations: list[dict[str, Any]] = Field(default_factory=list)
    metadata: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Batch jobs
# ---------------------------------------------------------------------------


class BatchJob(BaseModel):
    """A Mistral batch inference job (``/batch/jobs``)."""

    model_config = ConfigDict(frozen=True)

    id: str
    object: str = "batch"
    endpoint: str = ""
    model: Optional[str] = None
    agent_id: Optional[str] = None
    input_files: list[str] = Field(default_factory=list)
    output_file: Optional[str] = None
    error_file: Optional[str] = None
    errors: list[dict[str, Any]] = Field(default_factory=list)
    status: Optional[str] = None
    created_at: int = 0
    started_at: Optional[int] = None
    completed_at: Optional[int] = None
    total_requests: int = 0
    completed_requests: int = 0
    succeeded_requests: int = 0
    failed_requests: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class BatchJobDeleted(BaseModel):
    """Result of deleting a batch job (``DELETE /batch/jobs/{job_id}``)."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    object: str = "batch"
    deleted: bool = False


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------


class OCRPage(BaseModel):
    """A single page of an OCR result."""

    model_config = ConfigDict(frozen=True)

    index: int = 0
    markdown: str = ""
    images: list[dict[str, Any]] = Field(default_factory=list)
    tables: list[dict[str, Any]] = Field(default_factory=list)
    hyperlinks: list[str] = Field(default_factory=list)
    header: Optional[str] = None
    footer: Optional[str] = None
    dimensions: Optional[dict[str, Any]] = None


class OCRResult(BaseModel):
    """Response from the OCR endpoint (``POST /ocr``)."""

    model_config = ConfigDict(frozen=True)

    model: str = ""
    pages: list[OCRPage] = Field(default_factory=list)
    document_annotation: Optional[str] = None
    usage_info: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Moderation / classification
# ---------------------------------------------------------------------------


class ModerationResult(BaseModel):
    """Result of a Mistral moderation classification.

    Mistral returns per-category boolean flags and corresponding
    confidence scores for a single input.
    """

    model_config = ConfigDict(frozen=True)

    id: str = ""
    model: str = ""
    categories: dict[str, bool] = Field(default_factory=dict)
    category_scores: dict[str, float] = Field(default_factory=dict)


class ClassificationResult(BaseModel):
    """Result of a Mistral classification request.

    Returned by ``POST /classifications`` and ``POST /chat/classifications``.
    ``results`` is a list of per-input maps from classifier target name to
    its scores/labels payload.
    """

    model_config = ConfigDict(frozen=True)

    id: str = ""
    model: str = ""
    results: list[dict[str, Any]] = Field(default_factory=list)
