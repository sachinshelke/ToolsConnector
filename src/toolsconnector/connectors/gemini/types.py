"""Pydantic models for the Google Gemini connector.

All response models use ``frozen=True`` to enforce immutability. Field names
follow Python ``snake_case`` even though the Gemini REST API returns
``camelCase``; parsing maps between the two in
:mod:`toolsconnector.connectors.gemini._parsers`.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Shared / embedded models
# ---------------------------------------------------------------------------


class GeminiUsage(BaseModel):
    """Token usage statistics for a Gemini API call.

    Parsed from the ``usageMetadata`` object on a ``generateContent``
    response. All counts default to ``0`` when the field is absent.
    """

    model_config = ConfigDict(frozen=True)

    prompt_token_count: int = 0
    candidates_token_count: int = 0
    total_token_count: int = 0
    cached_content_token_count: int = 0


# ---------------------------------------------------------------------------
# Response models -- generation, tokens, embeddings
# ---------------------------------------------------------------------------


class GeminiResponse(BaseModel):
    """Parsed result of a ``generateContent`` call.

    The concatenated text of every part in the first candidate is exposed
    as ``text``; the raw candidate list is preserved on ``candidates`` for
    callers that need multi-candidate or non-text parts.
    """

    model_config = ConfigDict(frozen=True)

    text: str = ""
    finish_reason: Optional[str] = None
    model_version: Optional[str] = None
    usage: Optional[GeminiUsage] = None
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    prompt_feedback: Optional[dict[str, Any]] = None


class TokenCount(BaseModel):
    """Response from the ``countTokens`` endpoint."""

    model_config = ConfigDict(frozen=True)

    total_tokens: int = 0
    cached_content_token_count: int = 0


class Embedding(BaseModel):
    """A single embedding vector from ``embedContent``."""

    model_config = ConfigDict(frozen=True)

    values: list[float] = Field(default_factory=list)


class BatchEmbeddings(BaseModel):
    """Response from the ``batchEmbedContents`` endpoint."""

    model_config = ConfigDict(frozen=True)

    embeddings: list[Embedding] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class GeminiModel(BaseModel):
    """Metadata for an available Gemini model."""

    model_config = ConfigDict(frozen=True)

    name: str = ""
    version: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    input_token_limit: Optional[int] = None
    output_token_limit: Optional[int] = None
    supported_generation_methods: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Files API
# ---------------------------------------------------------------------------


class GeminiFile(BaseModel):
    """Metadata for a file uploaded via the Gemini Files API.

    Mirrors the ``File`` resource. ``name`` is the resource identifier in
    ``files/{id}`` form and ``uri`` is the value passed in a ``fileData``
    part when referencing the file from ``generateContent``.
    """

    model_config = ConfigDict(frozen=True)

    name: str = ""
    display_name: Optional[str] = None
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    create_time: Optional[str] = None
    update_time: Optional[str] = None
    expiration_time: Optional[str] = None
    sha256_hash: Optional[str] = None
    uri: Optional[str] = None
    download_uri: Optional[str] = None
    state: Optional[str] = None
    source: Optional[str] = None
    error: Optional[dict[str, Any]] = None
    video_metadata: Optional[dict[str, Any]] = None


class FileList(BaseModel):
    """A page of files from the ``files.list`` endpoint."""

    model_config = ConfigDict(frozen=True)

    files: list[GeminiFile] = Field(default_factory=list)
    next_page_token: Optional[str] = None


# ---------------------------------------------------------------------------
# Context caching (cachedContents)
# ---------------------------------------------------------------------------


class CacheUsage(BaseModel):
    """Usage metadata for a cached content resource (``usageMetadata``)."""

    model_config = ConfigDict(frozen=True)

    total_token_count: int = 0


class CachedContent(BaseModel):
    """A context cache resource (``cachedContents/{id}``).

    Caching lets a large, reused context (system instruction, documents,
    tools) be uploaded once and referenced by ``name`` on subsequent
    ``generateContent`` calls, lowering cost and latency.
    """

    model_config = ConfigDict(frozen=True)

    name: str = ""
    display_name: Optional[str] = None
    model: Optional[str] = None
    create_time: Optional[str] = None
    update_time: Optional[str] = None
    expire_time: Optional[str] = None
    usage: Optional[CacheUsage] = None
    contents: list[dict[str, Any]] = Field(default_factory=list)
    system_instruction: Optional[dict[str, Any]] = None
    tools: list[dict[str, Any]] = Field(default_factory=list)
    tool_config: Optional[dict[str, Any]] = None


class CachedContentList(BaseModel):
    """A page of cached contents from the ``cachedContents.list`` endpoint."""

    model_config = ConfigDict(frozen=True)

    cached_contents: list[CachedContent] = Field(default_factory=list)
    next_page_token: Optional[str] = None


# ---------------------------------------------------------------------------
# Tuned models
# ---------------------------------------------------------------------------


class TunedModel(BaseModel):
    """A tuned (fine-tuned) Gemini model (``tunedModels/{id}``).

    ``state`` is one of ``STATE_UNSPECIFIED``, ``CREATING``, ``ACTIVE``,
    or ``FAILED``. ``base_model`` is the foundation model the tuning task
    derived from, in ``models/{id}`` form.
    """

    model_config = ConfigDict(frozen=True)

    name: str = ""
    display_name: Optional[str] = None
    description: Optional[str] = None
    state: Optional[str] = None
    base_model: Optional[str] = None
    create_time: Optional[str] = None
    update_time: Optional[str] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    tuning_task: Optional[dict[str, Any]] = None
    tuned_model_source: Optional[dict[str, Any]] = None


class TunedModelList(BaseModel):
    """A page of tuned models from the ``tunedModels.list`` endpoint."""

    model_config = ConfigDict(frozen=True)

    tuned_models: list[TunedModel] = Field(default_factory=list)
    next_page_token: Optional[str] = None
