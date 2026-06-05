"""Pydantic models for Cohere connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Shared / embedded models
# ---------------------------------------------------------------------------


class Usage(BaseModel):
    """Token usage statistics for a Cohere API call.

    Mirrors the ``usage.tokens`` object returned by the v2 chat and
    embed endpoints (``input_tokens`` / ``output_tokens``).
    """

    model_config = ConfigDict(frozen=True)

    input_tokens: int = 0
    output_tokens: int = 0


# ---------------------------------------------------------------------------
# Response models -- inference (chat / embed / rerank / classify / tokenize)
# ---------------------------------------------------------------------------


class ChatResponse(BaseModel):
    """Response from the Cohere v2 chat endpoint.

    The assistant text is flattened from ``message.content[0].text`` for
    convenience; ``content_blocks`` preserves the raw content array.
    """

    model_config = ConfigDict(frozen=True)

    id: str = ""
    text: str = ""
    role: str = "assistant"
    finish_reason: Optional[str] = None
    content_blocks: list[dict[str, Any]] = Field(default_factory=list)
    usage: Optional[Usage] = None


class EmbedResponse(BaseModel):
    """Response from the Cohere v2 embed endpoint."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    embeddings: dict[str, list[list[float]]] = Field(default_factory=dict)
    texts: list[str] = Field(default_factory=list)
    usage: Optional[Usage] = None


class RerankResult(BaseModel):
    """A single ranked document from the rerank endpoint."""

    model_config = ConfigDict(frozen=True)

    index: int = 0
    relevance_score: float = 0.0


class RerankResponse(BaseModel):
    """Response from the Cohere v2 rerank endpoint."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    results: list[RerankResult] = Field(default_factory=list)


class ClassifyPrediction(BaseModel):
    """A single classification prediction for one input."""

    model_config = ConfigDict(frozen=True)

    input: str = ""
    prediction: Optional[str] = None
    confidence: Optional[float] = None
    labels: dict[str, Any] = Field(default_factory=dict)


class ClassifyResponse(BaseModel):
    """Response from the Cohere v1 classify endpoint."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    classifications: list[ClassifyPrediction] = Field(default_factory=list)


class TokenizeResponse(BaseModel):
    """Response from the Cohere v1 tokenize endpoint."""

    model_config = ConfigDict(frozen=True)

    tokens: list[int] = Field(default_factory=list)
    token_strings: list[str] = Field(default_factory=list)


class DetokenizeResponse(BaseModel):
    """Response from the Cohere v1 detokenize endpoint."""

    model_config = ConfigDict(frozen=True)

    text: str = ""


# ---------------------------------------------------------------------------
# Response models -- models
# ---------------------------------------------------------------------------


class CohereModel(BaseModel):
    """An available Cohere model.

    Returned by the v1 ``/models`` (list) and ``/models/{model}`` (get)
    endpoints.
    """

    model_config = ConfigDict(frozen=True)

    name: str = ""
    endpoints: list[str] = Field(default_factory=list)
    context_length: Optional[int] = None
    finetuned: bool = False
    tokenizer_url: Optional[str] = None
    default_endpoints: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Response models -- embed jobs (batch embeddings, /v1/embed-jobs)
# ---------------------------------------------------------------------------


class EmbedJob(BaseModel):
    """A Cohere batch embedding job from the v1 ``/embed-jobs`` endpoint.

    Created by :meth:`Cohere.create_embed_job` and inspected via
    :meth:`Cohere.get_embed_job` / :meth:`Cohere.list_embed_jobs`. The
    ``status`` progresses through ``processing`` -> ``complete`` (or
    ``cancelling`` -> ``cancelled`` / ``failed``).
    """

    model_config = ConfigDict(frozen=True)

    job_id: str = ""
    status: Optional[str] = None
    created_at: Optional[str] = None
    input_dataset_id: Optional[str] = None
    output_dataset_id: Optional[str] = None
    model: Optional[str] = None
    truncate: Optional[str] = None
    name: Optional[str] = None
    meta: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Response models -- datasets (/v1/datasets)
# ---------------------------------------------------------------------------


class DatasetPart(BaseModel):
    """A single underlying file ("part") of a Cohere dataset."""

    model_config = ConfigDict(frozen=True)

    name: Optional[str] = None
    url: Optional[str] = None
    index: Optional[int] = None
    size_bytes: Optional[int] = None
    num_rows: Optional[int] = None
    original_url: Optional[str] = None
    samples: list[str] = Field(default_factory=list)


class Dataset(BaseModel):
    """A Cohere dataset from the v1 ``/datasets`` endpoint.

    Datasets are validated, versioned collections of records used as
    inputs to embed jobs and fine-tuning. ``validation_status`` reflects
    the outcome of Cohere's schema validation (``validated`` /
    ``failed`` / ``processing`` / ``unknown``).
    """

    model_config = ConfigDict(frozen=True)

    id: str = ""
    name: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    dataset_type: Optional[str] = None
    validation_status: Optional[str] = None
    validation_error: Optional[str] = None
    schema_: Optional[str] = Field(default=None, alias="schema")
    required_fields: list[str] = Field(default_factory=list)
    preserve_fields: list[str] = Field(default_factory=list)
    dataset_parts: list[DatasetPart] = Field(default_factory=list)
    validation_warnings: list[str] = Field(default_factory=list)


class DatasetUsage(BaseModel):
    """Organization-wide dataset storage usage from ``/v1/datasets/usage``."""

    model_config = ConfigDict(frozen=True)

    organization_usage: int = 0


# ---------------------------------------------------------------------------
# Response models -- fine-tuning (/v1/finetuning)
# ---------------------------------------------------------------------------


class FinetunedModel(BaseModel):
    """A Cohere fine-tuned model from the v1 ``/finetuning`` endpoints.

    The ``settings`` object carries the base model, training dataset, and
    hyperparameters supplied at creation time, preserved here as a raw
    dict. ``status`` uses Cohere's ``STATUS_*`` enum (e.g.
    ``STATUS_QUEUED``, ``STATUS_FINETUNING``, ``STATUS_READY``).
    """

    model_config = ConfigDict(frozen=True)

    id: str = ""
    name: str = ""
    creator_id: Optional[str] = None
    organization_id: Optional[str] = None
    settings: dict[str, Any] = Field(default_factory=dict)
    status: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    completed_at: Optional[str] = None
    last_used: Optional[str] = None
    base_model: Optional[str] = None


# ---------------------------------------------------------------------------
# Response models -- auth (/v1/check-api-key)
# ---------------------------------------------------------------------------


class ApiKeyCheck(BaseModel):
    """Result of validating an API key via ``/v1/check-api-key``."""

    model_config = ConfigDict(frozen=True)

    valid: bool = False
    organization_id: Optional[str] = None
    owner_id: Optional[str] = None
