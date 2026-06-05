"""Cohere API response parsers.

Helper functions that turn raw JSON dicts from the Cohere REST API into
typed, frozen Pydantic models. Split out of ``connector.py`` so the
connector body stays focused on routing/HTTP and the per-object field
mapping lives in one place (mirrors the ``stripe/_parsers.py`` pattern).
"""

from __future__ import annotations

from typing import Any, Optional

from .types import (
    ApiKeyCheck,
    CohereModel,
    Dataset,
    DatasetPart,
    DatasetUsage,
    EmbedJob,
    FinetunedModel,
    Usage,
)


def parse_usage(usage_data: Optional[dict[str, Any]]) -> Optional[Usage]:
    """Parse a Cohere ``usage`` payload into a :class:`Usage` model.

    Cohere nests token counts under ``usage.tokens`` (``input_tokens`` /
    ``output_tokens``) on v2 endpoints.

    Args:
        usage_data: The raw ``usage`` dict from the response, or None.

    Returns:
        A populated Usage model, or None when no usage was returned.
    """
    if not usage_data:
        return None
    tokens = usage_data.get("tokens") or {}
    return Usage(
        input_tokens=tokens.get("input_tokens", 0),
        output_tokens=tokens.get("output_tokens", 0),
    )


def parse_model(data: dict[str, Any]) -> CohereModel:
    """Parse a single model object from ``/v1/models`` responses.

    Args:
        data: Raw model dict from the Cohere API.

    Returns:
        A CohereModel instance.
    """
    return CohereModel(
        name=data.get("name", ""),
        endpoints=data.get("endpoints") or [],
        context_length=data.get("context_length"),
        finetuned=data.get("finetuned", False),
        tokenizer_url=data.get("tokenizer_url"),
        default_endpoints=data.get("default_endpoints") or [],
    )


def parse_embed_job(data: dict[str, Any]) -> EmbedJob:
    """Parse a single embed-job object from ``/v1/embed-jobs`` responses.

    Args:
        data: Raw embed-job dict from the Cohere API.

    Returns:
        An EmbedJob instance.
    """
    return EmbedJob(
        job_id=data.get("job_id", ""),
        status=data.get("status"),
        created_at=data.get("created_at"),
        input_dataset_id=data.get("input_dataset_id"),
        output_dataset_id=data.get("output_dataset_id"),
        model=data.get("model"),
        truncate=data.get("truncate"),
        name=data.get("name"),
        meta=data.get("meta") or {},
    )


def parse_dataset(data: dict[str, Any]) -> Dataset:
    """Parse a single dataset object from ``/v1/datasets`` responses.

    Args:
        data: Raw dataset dict from the Cohere API.

    Returns:
        A Dataset instance.
    """
    parts = [
        DatasetPart(
            name=p.get("name"),
            url=p.get("url"),
            index=p.get("index"),
            size_bytes=p.get("size_bytes"),
            num_rows=p.get("num_rows"),
            original_url=p.get("original_url"),
            samples=p.get("samples") or [],
        )
        for p in data.get("dataset_parts") or []
    ]
    return Dataset(
        id=data.get("id", ""),
        name=data.get("name"),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
        dataset_type=data.get("dataset_type"),
        validation_status=data.get("validation_status"),
        validation_error=data.get("validation_error"),
        schema=data.get("schema"),
        required_fields=data.get("required_fields") or [],
        preserve_fields=data.get("preserve_fields") or [],
        dataset_parts=parts,
        validation_warnings=data.get("validation_warnings") or [],
    )


def parse_dataset_usage(data: dict[str, Any]) -> DatasetUsage:
    """Parse the ``/v1/datasets/usage`` response.

    Args:
        data: Raw usage dict from the Cohere API.

    Returns:
        A DatasetUsage instance.
    """
    return DatasetUsage(organization_usage=data.get("organization_usage", 0))


def parse_finetuned_model(data: dict[str, Any]) -> FinetunedModel:
    """Parse a single finetuned-model object from ``/v1/finetuning`` responses.

    Args:
        data: Raw finetuned-model dict from the Cohere API.

    Returns:
        A FinetunedModel instance.
    """
    return FinetunedModel(
        id=data.get("id", ""),
        name=data.get("name", ""),
        creator_id=data.get("creator_id"),
        organization_id=data.get("organization_id"),
        settings=data.get("settings") or {},
        status=data.get("status"),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
        completed_at=data.get("completed_at"),
        last_used=data.get("last_used"),
        base_model=data.get("base_model"),
    )


def parse_api_key_check(data: dict[str, Any]) -> ApiKeyCheck:
    """Parse the ``/v1/check-api-key`` response.

    Args:
        data: Raw check-api-key dict from the Cohere API.

    Returns:
        An ApiKeyCheck instance.
    """
    return ApiKeyCheck(
        valid=data.get("valid", False),
        organization_id=data.get("organization_id"),
        owner_id=data.get("owner_id"),
    )
