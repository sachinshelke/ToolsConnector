"""OpenAI connector -- chat completions, embeddings, images, audio, and assistants."""

from __future__ import annotations

from .connector import OpenAI
from .types import (
    Assistant,
    AudioTranscription,
    ChatCompletion,
    ChatMessage,
    Embedding,
    ImageResult,
    OpenAIFile,
    OpenAIModel,
    Thread,
    ThreadMessage,
    ThreadRun,
)

__all__ = [
    "OpenAI",
    "Assistant",
    "AudioTranscription",
    "ChatCompletion",
    "ChatMessage",
    "Embedding",
    "ImageResult",
    "OpenAIFile",
    "OpenAIModel",
    "Thread",
    "ThreadMessage",
    "ThreadRun",
]
