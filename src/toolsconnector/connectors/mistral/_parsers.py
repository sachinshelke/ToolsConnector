"""Mistral API response parsers.

Helper functions that turn raw JSON dicts from the Mistral REST API into
typed, frozen Pydantic models. Kept separate from ``connector.py`` so the
connector body stays focused on request construction and the action
surface, mirroring the ``stripe`` connector's ``_parsers.py`` split.
"""

from __future__ import annotations

from typing import Any, Optional

from .types import (
    AgentsCompletion,
    ArchiveModelResult,
    BatchJob,
    BatchJobDeleted,
    ChatChoice,
    ChatCompletion,
    ChatMessage,
    ClassificationResult,
    Embedding,
    EmbeddingData,
    FileDeleted,
    FileSignedURL,
    FIMCompletion,
    FineTuningJob,
    MistralFile,
    MistralModel,
    ModelDeleted,
    ModerationResult,
    OCRPage,
    OCRResult,
    Usage,
)


def parse_usage(usage_data: Optional[dict[str, Any]]) -> Optional[Usage]:
    """Parse a Mistral usage dict into a :class:`Usage` model.

    Args:
        usage_data: The raw ``usage`` object from a response, or None.

    Returns:
        A Usage model, or None when no usage data is present.
    """
    if not usage_data:
        return None
    return Usage(
        prompt_tokens=usage_data.get("prompt_tokens", 0),
        completion_tokens=usage_data.get("completion_tokens", 0),
        total_tokens=usage_data.get("total_tokens", 0),
    )


def parse_choices(raw_choices: list[dict[str, Any]]) -> list[ChatChoice]:
    """Parse a list of raw choice dicts into :class:`ChatChoice` models.

    Args:
        raw_choices: The raw ``choices`` array from a completion response.

    Returns:
        A list of ChatChoice models with nested messages.
    """
    return [
        ChatChoice(
            index=c.get("index", i),
            message=ChatMessage(
                role=c.get("message", {}).get("role", "assistant"),
                content=c.get("message", {}).get("content"),
                tool_calls=c.get("message", {}).get("tool_calls"),
            ),
            finish_reason=c.get("finish_reason"),
        )
        for i, c in enumerate(raw_choices)
    ]


def parse_chat_completion(data: dict[str, Any]) -> ChatCompletion:
    """Parse a chat completion response.

    Args:
        data: Raw JSON dict from ``POST /chat/completions``.

    Returns:
        A ChatCompletion model.
    """
    return ChatCompletion(
        id=data.get("id", ""),
        object=data.get("object", "chat.completion"),
        created=data.get("created", 0),
        model=data.get("model", ""),
        choices=parse_choices(data.get("choices", [])),
        usage=parse_usage(data.get("usage")),
    )


def parse_fim_completion(data: dict[str, Any]) -> FIMCompletion:
    """Parse a fill-in-the-middle completion response.

    Args:
        data: Raw JSON dict from ``POST /fim/completions``.

    Returns:
        A FIMCompletion model.
    """
    return FIMCompletion(
        id=data.get("id", ""),
        object=data.get("object", "chat.completion"),
        created=data.get("created", 0),
        model=data.get("model", ""),
        choices=parse_choices(data.get("choices", [])),
        usage=parse_usage(data.get("usage")),
    )


def parse_agents_completion(data: dict[str, Any]) -> AgentsCompletion:
    """Parse an agents completion response.

    Args:
        data: Raw JSON dict from ``POST /agents/completions``.

    Returns:
        An AgentsCompletion model.
    """
    return AgentsCompletion(
        id=data.get("id", ""),
        object=data.get("object", "chat.completion"),
        created=data.get("created", 0),
        model=data.get("model", ""),
        choices=parse_choices(data.get("choices", [])),
        usage=parse_usage(data.get("usage")),
    )


def parse_embedding(data: dict[str, Any]) -> Embedding:
    """Parse an embeddings response.

    Args:
        data: Raw JSON dict from ``POST /embeddings``.

    Returns:
        An Embedding model.
    """
    embedding_data = [
        EmbeddingData(
            index=e.get("index", i),
            embedding=e.get("embedding", []),
            object=e.get("object", "embedding"),
        )
        for i, e in enumerate(data.get("data", []))
    ]
    return Embedding(
        id=data.get("id", ""),
        object=data.get("object", "list"),
        data=embedding_data,
        model=data.get("model", ""),
        usage=parse_usage(data.get("usage")),
    )


def parse_model(data: dict[str, Any]) -> MistralModel:
    """Parse a single model card.

    Args:
        data: Raw JSON dict for one model (base or fine-tuned card).

    Returns:
        A MistralModel model.
    """
    return MistralModel(
        id=data.get("id", ""),
        object=data.get("object", "model"),
        created=data.get("created", 0),
        owned_by=data.get("owned_by", ""),
        name=data.get("name"),
        description=data.get("description"),
        max_context_length=data.get("max_context_length"),
        aliases=data.get("aliases") or [],
        capabilities=data.get("capabilities") or {},
        type=data.get("type"),
        root=data.get("root"),
        archived=data.get("archived"),
    )


def parse_model_deleted(data: dict[str, Any]) -> ModelDeleted:
    """Parse a delete-model response.

    Args:
        data: Raw JSON dict from ``DELETE /models/{model_id}``.

    Returns:
        A ModelDeleted model.
    """
    return ModelDeleted(
        id=data.get("id", ""),
        object=data.get("object", "model"),
        deleted=data.get("deleted", False),
    )


def parse_archive_result(data: dict[str, Any]) -> ArchiveModelResult:
    """Parse an (un)archive-model response.

    Args:
        data: Raw JSON dict from the fine-tuning model archive endpoints.

    Returns:
        An ArchiveModelResult model.
    """
    return ArchiveModelResult(
        id=data.get("id", ""),
        object=data.get("object", "model"),
        archived=data.get("archived", False),
    )


def parse_file(data: dict[str, Any]) -> MistralFile:
    """Parse a file object.

    Args:
        data: Raw JSON dict for one file (``FileSchema``).

    Returns:
        A MistralFile model.
    """
    return MistralFile(
        id=data.get("id", ""),
        object=data.get("object", "file"),
        size_bytes=data.get("size_bytes", data.get("bytes", 0)),
        created_at=data.get("created_at", 0),
        filename=data.get("filename", ""),
        purpose=data.get("purpose", ""),
        sample_type=data.get("sample_type"),
        num_lines=data.get("num_lines"),
        mimetype=data.get("mimetype"),
        source=data.get("source"),
    )


def parse_file_deleted(data: dict[str, Any]) -> FileDeleted:
    """Parse a delete-file response.

    Args:
        data: Raw JSON dict from ``DELETE /files/{file_id}``.

    Returns:
        A FileDeleted model.
    """
    return FileDeleted(
        id=data.get("id", ""),
        object=data.get("object", "file"),
        deleted=data.get("deleted", False),
    )


def parse_signed_url(data: dict[str, Any]) -> FileSignedURL:
    """Parse a signed-URL response.

    Args:
        data: Raw JSON dict from ``GET /files/{file_id}/url``.

    Returns:
        A FileSignedURL model.
    """
    return FileSignedURL(url=data.get("url", ""))


def parse_finetuning_job(data: dict[str, Any]) -> FineTuningJob:
    """Parse a fine-tuning job object.

    Args:
        data: Raw JSON dict for one fine-tuning job.

    Returns:
        A FineTuningJob model.
    """
    return FineTuningJob(
        id=data.get("id", ""),
        object=data.get("object", "job"),
        model=data.get("model", ""),
        status=data.get("status"),
        job_type=data.get("job_type"),
        created_at=data.get("created_at", 0),
        modified_at=data.get("modified_at", 0),
        training_files=data.get("training_files") or [],
        validation_files=data.get("validation_files") or [],
        fine_tuned_model=data.get("fine_tuned_model"),
        suffix=data.get("suffix"),
        auto_start=data.get("auto_start"),
        trained_tokens=data.get("trained_tokens"),
        hyperparameters=data.get("hyperparameters") or {},
        integrations=data.get("integrations") or [],
        metadata=data.get("metadata"),
    )


def parse_batch_job(data: dict[str, Any]) -> BatchJob:
    """Parse a batch job object.

    Args:
        data: Raw JSON dict for one batch job.

    Returns:
        A BatchJob model.
    """
    return BatchJob(
        id=data.get("id", ""),
        object=data.get("object", "batch"),
        endpoint=data.get("endpoint", ""),
        model=data.get("model"),
        agent_id=data.get("agent_id"),
        input_files=data.get("input_files") or [],
        output_file=data.get("output_file"),
        error_file=data.get("error_file"),
        errors=data.get("errors") or [],
        status=data.get("status"),
        created_at=data.get("created_at", 0),
        started_at=data.get("started_at"),
        completed_at=data.get("completed_at"),
        total_requests=data.get("total_requests", 0),
        completed_requests=data.get("completed_requests", 0),
        succeeded_requests=data.get("succeeded_requests", 0),
        failed_requests=data.get("failed_requests", 0),
        metadata=data.get("metadata") or {},
    )


def parse_batch_job_deleted(data: dict[str, Any]) -> BatchJobDeleted:
    """Parse a delete-batch-job response.

    Args:
        data: Raw JSON dict from ``DELETE /batch/jobs/{job_id}``.

    Returns:
        A BatchJobDeleted model.
    """
    return BatchJobDeleted(
        id=data.get("id", ""),
        object=data.get("object", "batch"),
        deleted=data.get("deleted", False),
    )


def parse_ocr_result(data: dict[str, Any]) -> OCRResult:
    """Parse an OCR response.

    Args:
        data: Raw JSON dict from ``POST /ocr``.

    Returns:
        An OCRResult model with one OCRPage per processed page.
    """
    pages = [
        OCRPage(
            index=p.get("index", i),
            markdown=p.get("markdown", ""),
            images=p.get("images") or [],
            tables=p.get("tables") or [],
            hyperlinks=p.get("hyperlinks") or [],
            header=p.get("header"),
            footer=p.get("footer"),
            dimensions=p.get("dimensions"),
        )
        for i, p in enumerate(data.get("pages", []))
    ]
    return OCRResult(
        model=data.get("model", ""),
        pages=pages,
        document_annotation=data.get("document_annotation"),
        usage_info=data.get("usage_info") or {},
    )


def parse_moderation(data: dict[str, Any]) -> ModerationResult:
    """Parse a moderation response into the first result's flags/scores.

    Args:
        data: Raw JSON dict from ``POST /moderations`` or
            ``POST /chat/moderations``.

    Returns:
        A ModerationResult model for the first input.
    """
    results = data.get("results", [])
    first = results[0] if results else {}
    return ModerationResult(
        id=data.get("id", ""),
        model=data.get("model", ""),
        categories=first.get("categories", {}),
        category_scores=first.get("category_scores", {}),
    )


def parse_classification(data: dict[str, Any]) -> ClassificationResult:
    """Parse a classification response.

    Args:
        data: Raw JSON dict from ``POST /classifications`` or
            ``POST /chat/classifications``.

    Returns:
        A ClassificationResult model preserving the per-input result maps.
    """
    return ClassificationResult(
        id=data.get("id", ""),
        model=data.get("model", ""),
        results=data.get("results") or [],
    )
