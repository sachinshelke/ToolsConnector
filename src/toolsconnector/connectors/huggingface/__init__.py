"""Hugging Face connector -- Inference tasks, chat completion, and Hub metadata."""

from __future__ import annotations

from .connector import HuggingFace
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

__all__ = [
    "HuggingFace",
    "HFChatChoice",
    "HFChatCompletion",
    "HFChatMessage",
    "HFClassification",
    "HFDatasetInfo",
    "HFFillMaskToken",
    "HFGeneratedText",
    "HFImageSegment",
    "HFModelInfo",
    "HFObjectDetection",
    "HFQuestionAnswer",
    "HFSpaceInfo",
    "HFTableQuestionAnswer",
    "HFTokenClassification",
    "HFTranscription",
    "HFUsage",
    "HFWhoAmI",
    "HFZeroShotResult",
]
