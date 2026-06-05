"""Hugging Face response parsers.

Helper functions to normalise the heterogeneous Inference API and Hub
JSON payloads into the connector's typed Pydantic models. Extracted to
keep ``connector.py`` focused on action definitions.
"""

from __future__ import annotations

from typing import Any

from .types import (
    HFChatChoice,
    HFChatCompletion,
    HFChatMessage,
    HFClassification,
    HFDatasetInfo,
    HFFillMaskToken,
    HFGeneratedText,
    HFImageSegment,
    HFModelInfo,
    HFObjectDetection,
    HFQuestionAnswer,
    HFSpaceInfo,
    HFTableQuestionAnswer,
    HFTokenClassification,
    HFTranscription,
    HFUsage,
    HFWhoAmI,
    HFZeroShotResult,
)

# ---------------------------------------------------------------------------
# Shape normalisation
# ---------------------------------------------------------------------------


def as_rows(data: Any) -> list[dict[str, Any]]:
    """Normalise an inference payload to a flat list of result dicts.

    Wraps a bare dict in a list and flattens the one-level nesting the
    API uses for single text-classification inputs.

    Args:
        data: Raw parsed JSON from an Inference API task.

    Returns:
        A flat list of result dicts.
    """
    items = data if isinstance(data, list) else [data]
    rows: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, list):
            rows.extend(item)
        else:
            rows.append(item)
    return rows


def first_dict(data: Any) -> dict[str, Any]:
    """Unwrap a single-element list to its dict, else return the dict as-is.

    Several tasks (zero-shot, QA, table-QA) return either a bare dict or
    a single-element list wrapping that dict, depending on the provider.

    Args:
        data: Raw parsed JSON from an Inference API task.

    Returns:
        The result dict (empty dict if the payload was empty).
    """
    if isinstance(data, list):
        data = data[0] if data else {}
    return data if isinstance(data, dict) else {}


# ---------------------------------------------------------------------------
# Inference task parsers
# ---------------------------------------------------------------------------


def parse_classification(data: Any) -> list[HFClassification]:
    """Parse a label/score classification payload into HFClassification rows.

    Args:
        data: Raw classification payload (list, list-of-lists, or dict).

    Returns:
        A list of HFClassification pairs.
    """
    return [
        HFClassification(label=r.get("label", ""), score=r.get("score", 0.0)) for r in as_rows(data)
    ]


def parse_token_classification(data: Any) -> list[HFTokenClassification]:
    """Parse a token-classification payload into HFTokenClassification rows.

    Args:
        data: Raw token-classification payload.

    Returns:
        A list of HFTokenClassification entity spans.
    """
    return [
        HFTokenClassification(
            entity_group=r.get("entity_group"),
            entity=r.get("entity"),
            score=r.get("score", 0.0),
            word=r.get("word", ""),
            start=r.get("start"),
            end=r.get("end"),
        )
        for r in as_rows(data)
    ]


def parse_fill_mask(data: Any) -> list[HFFillMaskToken]:
    """Parse a fill-mask payload into HFFillMaskToken candidates.

    Args:
        data: Raw fill-mask payload.

    Returns:
        A list of HFFillMaskToken candidates ordered by score.
    """
    return [
        HFFillMaskToken(
            sequence=r.get("sequence", ""),
            score=r.get("score", 0.0),
            token=r.get("token"),
            token_str=r.get("token_str", ""),
        )
        for r in as_rows(data)
    ]


def parse_zero_shot(data: Any) -> HFZeroShotResult:
    """Parse a zero-shot-classification payload into HFZeroShotResult.

    Args:
        data: Raw zero-shot payload (dict or single-element list).

    Returns:
        An HFZeroShotResult with index-aligned labels and scores.
    """
    d = first_dict(data)
    return HFZeroShotResult(
        sequence=d.get("sequence", ""),
        labels=d.get("labels", []),
        scores=d.get("scores", []),
    )


def parse_question_answer(data: Any) -> HFQuestionAnswer:
    """Parse an extractive question-answering payload into HFQuestionAnswer.

    Args:
        data: Raw QA payload (dict or single-element list).

    Returns:
        An HFQuestionAnswer with the answer span, score, and offsets.
    """
    d = first_dict(data)
    return HFQuestionAnswer(
        answer=d.get("answer", ""),
        score=d.get("score", 0.0),
        start=d.get("start", 0),
        end=d.get("end", 0),
    )


def parse_table_question_answer(data: Any) -> HFTableQuestionAnswer:
    """Parse a table-question-answering payload into HFTableQuestionAnswer.

    Args:
        data: Raw table-QA payload (dict or single-element list).

    Returns:
        An HFTableQuestionAnswer with answer, coordinates, cells, and
        aggregator.
    """
    d = first_dict(data)
    return HFTableQuestionAnswer(
        answer=d.get("answer", ""),
        coordinates=d.get("coordinates", []),
        cells=d.get("cells", []),
        aggregator=d.get("aggregator"),
    )


def parse_object_detection(data: Any) -> list[HFObjectDetection]:
    """Parse an object-detection payload into HFObjectDetection rows.

    Args:
        data: Raw object-detection payload.

    Returns:
        A list of HFObjectDetection rows with bounding boxes.
    """
    return [
        HFObjectDetection(
            label=r.get("label", ""),
            score=r.get("score", 0.0),
            box=r.get("box", {}),
        )
        for r in as_rows(data)
    ]


def parse_image_segments(data: Any) -> list[HFImageSegment]:
    """Parse an image-segmentation payload into HFImageSegment rows.

    Args:
        data: Raw image-segmentation payload.

    Returns:
        A list of HFImageSegment rows, each carrying a base64 mask.
    """
    return [
        HFImageSegment(
            label=r.get("label", ""),
            score=r.get("score", 0.0),
            mask=r.get("mask", ""),
        )
        for r in as_rows(data)
    ]


def parse_transcription(data: Any) -> HFTranscription:
    """Parse an automatic-speech-recognition payload into HFTranscription.

    Args:
        data: Raw ASR payload (dict, or single-element list of dicts).

    Returns:
        An HFTranscription with the recognised text and optional chunks.
    """
    d = first_dict(data)
    return HFTranscription(
        text=d.get("text", ""),
        chunks=d.get("chunks") or [],
    )


def parse_generated_rows(data: Any, key: str) -> list[HFGeneratedText]:
    """Parse a text-to-text payload, reading ``key`` from each row.

    Args:
        data: Raw payload (list of dicts or a bare dict).
        key: The result key to read (``generated_text``, ``summary_text``,
            or ``translation_text``).

    Returns:
        A list of HFGeneratedText with the named field populated.
    """
    return [HFGeneratedText(**{key: r.get(key)}) for r in as_rows(data)]


# ---------------------------------------------------------------------------
# Chat completion parser
# ---------------------------------------------------------------------------


def parse_chat_completion(data: dict[str, Any]) -> HFChatCompletion:
    """Parse an OpenAI-compatible chat completion payload.

    Args:
        data: Raw chat completion response dict from the router endpoint.

    Returns:
        An HFChatCompletion with choices and usage statistics.
    """
    choices = [
        HFChatChoice(
            index=c.get("index", i),
            message=HFChatMessage(
                role=c.get("message", {}).get("role", "assistant"),
                content=c.get("message", {}).get("content"),
                tool_calls=c.get("message", {}).get("tool_calls"),
            ),
            finish_reason=c.get("finish_reason"),
        )
        for i, c in enumerate(data.get("choices", []))
    ]

    usage_data = data.get("usage")
    usage = (
        HFUsage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )
        if usage_data
        else None
    )

    return HFChatCompletion(
        id=data.get("id", ""),
        object=data.get("object", "chat.completion"),
        created=data.get("created", 0),
        model=data.get("model", ""),
        choices=choices,
        usage=usage,
        system_fingerprint=data.get("system_fingerprint"),
    )


# ---------------------------------------------------------------------------
# Hub parsers
# ---------------------------------------------------------------------------


def parse_model_info(m: dict[str, Any]) -> HFModelInfo:
    """Parse a Hub model dict into an HFModelInfo.

    Args:
        m: Raw model dict from the Hub API.

    Returns:
        An HFModelInfo.
    """
    return HFModelInfo(
        id=m.get("id", m.get("modelId", "")),
        author=m.get("author"),
        sha=m.get("sha"),
        pipeline_tag=m.get("pipeline_tag"),
        library_name=m.get("library_name"),
        private=m.get("private", False),
        gated=m.get("gated", False),
        disabled=m.get("disabled", False),
        downloads=m.get("downloads", 0),
        likes=m.get("likes", 0),
        last_modified=m.get("lastModified"),
        created_at=m.get("createdAt"),
        tags=m.get("tags", []),
        siblings=m.get("siblings") or [],
    )


def parse_dataset_info(d: dict[str, Any]) -> HFDatasetInfo:
    """Parse a Hub dataset dict into an HFDatasetInfo.

    Args:
        d: Raw dataset dict from the Hub API.

    Returns:
        An HFDatasetInfo.
    """
    return HFDatasetInfo(
        id=d.get("id", ""),
        author=d.get("author"),
        sha=d.get("sha"),
        private=d.get("private", False),
        gated=d.get("gated", False),
        disabled=d.get("disabled", False),
        downloads=d.get("downloads", 0),
        likes=d.get("likes", 0),
        last_modified=d.get("lastModified"),
        created_at=d.get("createdAt"),
        tags=d.get("tags", []),
        siblings=d.get("siblings") or [],
    )


def parse_space_info(s: dict[str, Any]) -> HFSpaceInfo:
    """Parse a Hub Space dict into an HFSpaceInfo.

    Args:
        s: Raw Space dict from the Hub API.

    Returns:
        An HFSpaceInfo.
    """
    return HFSpaceInfo(
        id=s.get("id", ""),
        author=s.get("author"),
        sha=s.get("sha"),
        sdk=s.get("sdk"),
        runtime=s.get("runtime"),
        private=s.get("private", False),
        gated=s.get("gated", False),
        disabled=s.get("disabled", False),
        likes=s.get("likes", 0),
        last_modified=s.get("lastModified"),
        created_at=s.get("createdAt"),
        tags=s.get("tags", []),
    )


def parse_whoami(data: dict[str, Any]) -> HFWhoAmI:
    """Parse a ``/whoami-v2`` payload into HFWhoAmI.

    Args:
        data: Raw identity dict from the Hub API.

    Returns:
        An HFWhoAmI.
    """
    return HFWhoAmI(
        name=data.get("name", ""),
        type=data.get("type", ""),
        email=data.get("email"),
        orgs=data.get("orgs", []),
    )
