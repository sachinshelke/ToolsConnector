"""Pydantic models for the Hugging Face connector.

All response models use ``frozen=True`` to enforce immutability. Hugging
Face Inference API outputs are heterogeneous (the JSON shape depends on the
model's task), so only the *stable* per-task shapes are modelled here.
Embeddings are returned as raw nested float lists rather than a model,
because their dimensionality is model-specific; binary tasks (text-to-image,
text-to-speech) return raw ``bytes``, and segmentation masks are surfaced as
base64-encoded PNG strings on a typed model.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Inference API result models (stable per-task shapes)
# ---------------------------------------------------------------------------


class HFGeneratedText(BaseModel):
    """A single text-generation / summarization / translation result.

    Different text-to-text tasks populate different keys, so all are
    optional on one model:

    - ``generated_text`` — text-generation / image-to-text output.
    - ``summary_text`` — summarization output.
    - ``translation_text`` — translation output.
    """

    model_config = ConfigDict(frozen=True)

    generated_text: Optional[str] = None
    summary_text: Optional[str] = None
    translation_text: Optional[str] = None


class HFClassification(BaseModel):
    """A single (label, score) pair from a classification task.

    Shared by text-classification, image-classification, and
    audio-classification — all of which return label/score pairs.
    """

    model_config = ConfigDict(frozen=True)

    label: str = ""
    score: float = 0.0


class HFTokenClassification(BaseModel):
    """A single token-classification (NER / PoS) entity span.

    ``entity_group`` is populated when an aggregation strategy groups
    consecutive tokens; ``entity`` is populated for ungrouped single
    tokens. ``start``/``end`` are character offsets into the input.
    """

    model_config = ConfigDict(frozen=True)

    entity_group: Optional[str] = None
    entity: Optional[str] = None
    score: float = 0.0
    word: str = ""
    start: Optional[int] = None
    end: Optional[int] = None


class HFFillMaskToken(BaseModel):
    """A single fill-mask candidate for a masked token."""

    model_config = ConfigDict(frozen=True)

    sequence: str = ""
    score: float = 0.0
    token: Optional[int] = None
    token_str: str = ""


class HFZeroShotResult(BaseModel):
    """Result of a zero-shot classification request.

    ``labels`` and ``scores`` are index-aligned and sorted by descending
    score.
    """

    model_config = ConfigDict(frozen=True)

    sequence: str = ""
    labels: list[str] = Field(default_factory=list)
    scores: list[float] = Field(default_factory=list)


class HFQuestionAnswer(BaseModel):
    """Result of an extractive question-answering request."""

    model_config = ConfigDict(frozen=True)

    answer: str = ""
    score: float = 0.0
    start: int = 0
    end: int = 0


class HFTableQuestionAnswer(BaseModel):
    """Result of a table-question-answering request.

    ``answer`` may be prefixed by ``"AGGREGATOR > "`` when the model
    applies an aggregation (e.g. ``SUM``). ``coordinates`` are
    ``[row, column]`` index pairs for the answer cells, ``cells`` are the
    raw cell values, and ``aggregator`` names the aggregation, if any.
    """

    model_config = ConfigDict(frozen=True)

    answer: str = ""
    coordinates: list[list[int]] = Field(default_factory=list)
    cells: list[str] = Field(default_factory=list)
    aggregator: Optional[str] = None


class HFObjectDetection(BaseModel):
    """A single detected object with its bounding box.

    ``box`` carries the integer pixel coordinates
    (``xmin``/``ymin``/``xmax``/``ymax``) of the detection.
    """

    model_config = ConfigDict(frozen=True)

    label: str = ""
    score: float = 0.0
    box: dict[str, int] = Field(default_factory=dict)


class HFImageSegment(BaseModel):
    """A single image-segmentation segment.

    ``mask`` is a base64-encoded black-and-white PNG covering the pixels
    belonging to this segment.
    """

    model_config = ConfigDict(frozen=True)

    label: str = ""
    score: float = 0.0
    mask: str = ""


class HFTranscription(BaseModel):
    """Result of an automatic-speech-recognition request.

    ``chunks`` is populated only when timestamps are requested; each
    chunk carries its text and ``[start, end]`` timestamp pair.
    """

    model_config = ConfigDict(frozen=True)

    text: str = ""
    chunks: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Chat completion models (OpenAI-compatible router endpoint)
# ---------------------------------------------------------------------------


class HFUsage(BaseModel):
    """Token usage statistics for a chat completion."""

    model_config = ConfigDict(frozen=True)

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class HFChatMessage(BaseModel):
    """A single message in a chat completion choice.

    ``tool_calls`` is populated when the model requests one or more tool
    invocations; its raw OpenAI-shaped list is passed through untyped.
    """

    model_config = ConfigDict(frozen=True)

    role: str = "assistant"
    content: Optional[str] = None
    tool_calls: Optional[list[dict[str, Any]]] = None


class HFChatChoice(BaseModel):
    """A single choice returned by a chat completion."""

    model_config = ConfigDict(frozen=True)

    index: int = 0
    message: HFChatMessage = Field(default_factory=HFChatMessage)
    finish_reason: Optional[str] = None


class HFChatCompletion(BaseModel):
    """A chat completion response from the OpenAI-compatible router."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    object: str = "chat.completion"
    created: int = 0
    model: str = ""
    choices: list[HFChatChoice] = Field(default_factory=list)
    usage: Optional[HFUsage] = None
    system_fingerprint: Optional[str] = None


# ---------------------------------------------------------------------------
# Hub API models
# ---------------------------------------------------------------------------


class HFModelInfo(BaseModel):
    """Metadata for a model on the Hugging Face Hub.

    The ``downloads_all_time``, ``safetensors``, ``config``, ``card_data``,
    and ``inference_provider_mapping`` fields are only populated when the
    matching ``expand`` value is requested via ``get_model(expand=[...])``;
    they stay ``None`` otherwise.
    """

    model_config = ConfigDict(frozen=True)

    id: str = ""
    author: Optional[str] = None
    sha: Optional[str] = None
    pipeline_tag: Optional[str] = None
    library_name: Optional[str] = None
    private: bool = False
    gated: Any = False
    disabled: bool = False
    downloads: int = 0
    downloads_all_time: Optional[int] = None
    likes: int = 0
    last_modified: Optional[str] = None
    created_at: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    siblings: list[dict[str, Any]] = Field(default_factory=list)
    # Populated only when requested via ``get_model(expand=[...])``.
    safetensors: Optional[dict[str, Any]] = None
    config: Optional[dict[str, Any]] = None
    card_data: Optional[dict[str, Any]] = None
    inference_provider_mapping: Optional[dict[str, Any]] = None


class HFProviderPricing(BaseModel):
    """Per-token pricing for a model on a given inference provider.

    Values are USD per 1M tokens, as reported by the Inference Providers
    router catalog. Either field may be ``None`` if the provider does not
    report it.
    """

    model_config = ConfigDict(frozen=True)

    input: Optional[float] = None
    output: Optional[float] = None


class HFModelProvider(BaseModel):
    """A provider offering a model in the Inference Providers router catalog.

    Carries the routing status, the provider's max context window, per-token
    pricing, capability flags, and observed latency/throughput.
    """

    model_config = ConfigDict(frozen=True)

    provider: str = ""
    status: Optional[str] = None
    context_length: Optional[int] = None
    pricing: Optional[HFProviderPricing] = None
    supports_tools: Optional[bool] = None
    supports_structured_output: Optional[bool] = None
    first_token_latency_ms: Optional[float] = None
    throughput: Optional[float] = None
    is_model_author: bool = False


class HFCatalogModel(BaseModel):
    """A model entry in the Inference Providers router catalog (``/v1/models``).

    Aggregates every provider serving the model, each with its own pricing,
    context window, and capabilities -- the basis for model / provider /
    cost comparison.
    """

    model_config = ConfigDict(frozen=True)

    id: str = ""
    owned_by: Optional[str] = None
    created: Optional[int] = None
    input_modalities: list[str] = Field(default_factory=list)
    output_modalities: list[str] = Field(default_factory=list)
    providers: list[HFModelProvider] = Field(default_factory=list)


class HFInferenceProvider(BaseModel):
    """A single inference provider that serves a given Hub model.

    Flattened from the Hub's ``inferenceProviderMapping`` object: ``provider``
    is the partner name (e.g. ``'novita'``, ``'together'``), ``status`` is its
    routing state (``'live'`` / ``'staging'``), ``provider_id`` is the model id
    on the provider's own side, and ``task`` is the served pipeline.
    """

    model_config = ConfigDict(frozen=True)

    provider: str = ""
    status: Optional[str] = None
    provider_id: Optional[str] = None
    task: Optional[str] = None
    is_model_author: bool = False


class HFRepoFile(BaseModel):
    """A file or directory entry in a Hub repo's file tree.

    ``type`` is ``'file'`` or ``'directory'``; ``size`` is in bytes (the
    resolved LFS size for large files); ``lfs`` carries the LFS pointer
    metadata when the file is stored via Git LFS.
    """

    model_config = ConfigDict(frozen=True)

    path: str = ""
    type: str = ""
    size: int = 0
    oid: Optional[str] = None
    lfs: Optional[dict[str, Any]] = None


class HFDatasetInfo(BaseModel):
    """Metadata for a dataset on the Hugging Face Hub."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    author: Optional[str] = None
    sha: Optional[str] = None
    private: bool = False
    gated: Any = False
    disabled: bool = False
    downloads: int = 0
    likes: int = 0
    last_modified: Optional[str] = None
    created_at: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    siblings: list[dict[str, Any]] = Field(default_factory=list)


class HFSpaceInfo(BaseModel):
    """Metadata for a Space on the Hugging Face Hub."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    author: Optional[str] = None
    sha: Optional[str] = None
    sdk: Optional[str] = None
    runtime: Optional[dict[str, Any]] = None
    private: bool = False
    gated: Any = False
    disabled: bool = False
    likes: int = 0
    last_modified: Optional[str] = None
    created_at: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


class HFWhoAmI(BaseModel):
    """Identity returned by the Hub ``/whoami-v2`` token-check endpoint."""

    model_config = ConfigDict(frozen=True)

    name: str = ""
    type: str = ""
    email: Optional[str] = None
    orgs: list[dict[str, Any]] = Field(default_factory=list)
