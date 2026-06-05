"""Google Gemini API response parsers.

Helper functions that map raw ``camelCase`` JSON dicts from the Gemini REST
API into the typed, frozen Pydantic models declared in
:mod:`toolsconnector.connectors.gemini.types`. Keeping the JSON-to-model
mapping here keeps ``connector.py`` focused on HTTP and action wiring.
"""

from __future__ import annotations

from typing import Any

from .types import (
    CachedContent,
    CacheUsage,
    GeminiFile,
    GeminiModel,
    GeminiResponse,
    GeminiUsage,
    TunedModel,
)


def parse_model(data: dict[str, Any]) -> GeminiModel:
    """Map a raw model dict into a :class:`GeminiModel`.

    Args:
        data: A single ``Model`` object from the Gemini API.

    Returns:
        The parsed GeminiModel.
    """
    return GeminiModel(
        name=data.get("name", ""),
        version=data.get("version"),
        display_name=data.get("displayName"),
        description=data.get("description"),
        input_token_limit=data.get("inputTokenLimit"),
        output_token_limit=data.get("outputTokenLimit"),
        supported_generation_methods=data.get("supportedGenerationMethods", []),
    )


def parse_usage(data: dict[str, Any] | None) -> GeminiUsage | None:
    """Map a ``usageMetadata`` dict into a :class:`GeminiUsage`.

    Args:
        data: The ``usageMetadata`` object, or ``None`` when absent.

    Returns:
        The parsed GeminiUsage, or ``None`` when ``data`` is falsy.
    """
    if not data:
        return None
    return GeminiUsage(
        prompt_token_count=data.get("promptTokenCount", 0),
        candidates_token_count=data.get("candidatesTokenCount", 0),
        total_token_count=data.get("totalTokenCount", 0),
        cached_content_token_count=data.get("cachedContentTokenCount", 0),
    )


def parse_generate_response(data: dict[str, Any]) -> GeminiResponse:
    """Map a ``generateContent`` response into a :class:`GeminiResponse`.

    Concatenates the text of every part in the first candidate while
    preserving the raw candidate list for non-text or multi-candidate use.

    Args:
        data: The raw ``generateContent`` response body.

    Returns:
        The parsed GeminiResponse.
    """
    candidates: list[dict[str, Any]] = data.get("candidates", [])
    first = candidates[0] if candidates else {}
    parts = first.get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))

    return GeminiResponse(
        text=text,
        finish_reason=first.get("finishReason"),
        model_version=data.get("modelVersion"),
        usage=parse_usage(data.get("usageMetadata")),
        candidates=candidates,
        prompt_feedback=data.get("promptFeedback"),
    )


def parse_file(data: dict[str, Any]) -> GeminiFile:
    """Map a raw ``File`` dict into a :class:`GeminiFile`.

    The Files API wraps single-file responses in a ``{"file": {...}}``
    envelope on upload but returns the bare resource on ``get``; this
    accepts either by unwrapping a ``file`` key when present.

    Args:
        data: A ``File`` resource, optionally wrapped in ``{"file": ...}``.

    Returns:
        The parsed GeminiFile.
    """
    if "file" in data and isinstance(data["file"], dict):
        data = data["file"]
    return GeminiFile(
        name=data.get("name", ""),
        display_name=data.get("displayName"),
        mime_type=data.get("mimeType"),
        size_bytes=_to_int(data.get("sizeBytes")),
        create_time=data.get("createTime"),
        update_time=data.get("updateTime"),
        expiration_time=data.get("expirationTime"),
        sha256_hash=data.get("sha256Hash"),
        uri=data.get("uri"),
        download_uri=data.get("downloadUri"),
        state=data.get("state"),
        source=data.get("source"),
        error=data.get("error"),
        video_metadata=data.get("videoMetadata"),
    )


def parse_cached_content(data: dict[str, Any]) -> CachedContent:
    """Map a raw ``CachedContent`` dict into a :class:`CachedContent`.

    Args:
        data: A ``CachedContent`` resource from the caching API.

    Returns:
        The parsed CachedContent.
    """
    usage_data = data.get("usageMetadata")
    usage = (
        CacheUsage(total_token_count=usage_data.get("totalTokenCount", 0)) if usage_data else None
    )
    return CachedContent(
        name=data.get("name", ""),
        display_name=data.get("displayName"),
        model=data.get("model"),
        create_time=data.get("createTime"),
        update_time=data.get("updateTime"),
        expire_time=data.get("expireTime"),
        usage=usage,
        contents=data.get("contents", []),
        system_instruction=data.get("systemInstruction"),
        tools=data.get("tools", []),
        tool_config=data.get("toolConfig"),
    )


def parse_tuned_model(data: dict[str, Any]) -> TunedModel:
    """Map a raw ``TunedModel`` dict into a :class:`TunedModel`.

    Args:
        data: A ``TunedModel`` resource from the tuning API.

    Returns:
        The parsed TunedModel.
    """
    return TunedModel(
        name=data.get("name", ""),
        display_name=data.get("displayName"),
        description=data.get("description"),
        state=data.get("state"),
        base_model=data.get("baseModel"),
        create_time=data.get("createTime"),
        update_time=data.get("updateTime"),
        temperature=data.get("temperature"),
        top_p=data.get("topP"),
        top_k=data.get("topK"),
        tuning_task=data.get("tuningTask"),
        tuned_model_source=data.get("tunedModelSource"),
    )


def _to_int(value: Any) -> int | None:
    """Coerce an API numeric field to ``int``.

    The Gemini API serialises ``int64`` fields (e.g. ``sizeBytes``) as
    JSON strings; this normalises those into Python ``int`` while passing
    through ``None`` and unparseable values untouched.

    Args:
        value: The raw value (``str``, ``int``, or ``None``).

    Returns:
        The integer value, or ``None`` if absent/unparseable.
    """
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
