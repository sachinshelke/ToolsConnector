"""OpenAI connector -- chat completions, embeddings, images, audio, and assistants.

Uses httpx for direct HTTP calls against the OpenAI REST API v1.
Expects a Bearer API key passed as ``credentials``.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import (
    ConnectorCategory,
    ProtocolType,
    RateLimitSpec,
)
from toolsconnector.types import PageState, PaginatedList

from .types import (
    Assistant,
    AudioTranscription,
    ChatCompletion,
    ChatChoice,
    ChatMessage,
    Embedding,
    EmbeddingData,
    ImageData,
    ImageResult,
    OpenAIFile,
    OpenAIModel,
    ToolDefinition,
    Usage,
)

logger = logging.getLogger("toolsconnector.openai")


class OpenAI(BaseConnector):
    """Connect to OpenAI for chat completions, embeddings, images, audio, and assistants.

    Supports Bearer token authentication. Pass an API key as
    ``credentials`` when instantiating. Uses the OpenAI REST API v1
    via direct httpx calls.
    """

    name = "openai"
    display_name = "OpenAI"
    category = ConnectorCategory.AI_ML
    protocol = ProtocolType.REST
    base_url = "https://api.openai.com/v1"
    description = (
        "Connect to OpenAI for chat completions, embeddings, "
        "image generation, audio transcription, and assistants management."
    )
    _rate_limit_config = RateLimitSpec(rate=60, period=60, burst=20)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_headers(self) -> dict[str, str]:
        """Build authorization headers for OpenAI API requests.

        Returns:
            Dict with Authorization bearer header and content type.
        """
        return {
            "Authorization": f"Bearer {self._credentials}",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute an authenticated HTTP request against the OpenAI API.

        Args:
            method: HTTP method (GET, POST, DELETE, etc.).
            path: API path relative to base_url.
            **kwargs: Additional keyword arguments passed to httpx.

        Returns:
            Parsed JSON response as a dict.

        Raises:
            httpx.HTTPStatusError: If the API returns a non-2xx status.
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.request(
                method,
                f"{self._base_url}{path}",
                headers=self._get_headers(),
                **kwargs,
            )
            response.raise_for_status()
            if response.status_code == 204 or not response.content:
                return {}
            return response.json()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    @action("Create a chat completion")
    async def chat_completion(
        self,
        model: str,
        messages: list[dict[str, Any]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> ChatCompletion:
        """Create a chat completion using the specified model.

        Args:
            model: Model ID to use (e.g., 'gpt-4', 'gpt-4o', 'gpt-3.5-turbo').
            messages: List of message dicts with 'role' and 'content' keys.
            temperature: Sampling temperature between 0 and 2.
            max_tokens: Maximum number of tokens to generate.
            tools: List of tool definitions for function calling.

        Returns:
            ChatCompletion with generated message choices and usage stats.
        """
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if tools is not None:
            payload["tools"] = tools

        data = await self._request("POST", "/chat/completions", json=payload)

        choices = [
            ChatChoice(
                index=c.get("index", i),
                message=ChatMessage(
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
            Usage(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
            )
            if usage_data
            else None
        )

        return ChatCompletion(
            id=data.get("id", ""),
            object=data.get("object", "chat.completion"),
            created=data.get("created", 0),
            model=data.get("model", ""),
            choices=choices,
            usage=usage,
            system_fingerprint=data.get("system_fingerprint"),
        )

    @action("List available models", idempotent=True)
    async def list_models(self) -> list[OpenAIModel]:
        """List all models available to the authenticated account.

        Returns:
            List of OpenAIModel objects with model metadata.
        """
        data = await self._request("GET", "/models")

        return [
            OpenAIModel(
                id=m.get("id", ""),
                object=m.get("object", "model"),
                created=m.get("created", 0),
                owned_by=m.get("owned_by", ""),
            )
            for m in data.get("data", [])
        ]

    @action("Create text embeddings")
    async def create_embedding(
        self,
        model: str,
        input: str,
    ) -> Embedding:
        """Create an embedding vector for the given input text.

        Args:
            model: Model ID to use (e.g., 'text-embedding-3-small').
            input: The text to embed.

        Returns:
            Embedding response with vector data and usage statistics.
        """
        payload: dict[str, Any] = {
            "model": model,
            "input": input,
        }

        data = await self._request("POST", "/embeddings", json=payload)

        embedding_data = [
            EmbeddingData(
                index=e.get("index", i),
                embedding=e.get("embedding", []),
                object=e.get("object", "embedding"),
            )
            for i, e in enumerate(data.get("data", []))
        ]

        usage_data = data.get("usage")
        usage = (
            Usage(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
            )
            if usage_data
            else None
        )

        return Embedding(
            object=data.get("object", "list"),
            data=embedding_data,
            model=data.get("model", ""),
            usage=usage,
        )

    @action("Generate images from a text prompt")
    async def create_image(
        self,
        prompt: str,
        size: Optional[str] = None,
        n: Optional[int] = None,
    ) -> ImageResult:
        """Generate images from a text prompt using DALL-E.

        Args:
            prompt: A text description of the desired image(s).
            size: Image size ('256x256', '512x512', '1024x1024', '1792x1024', '1024x1792').
            n: Number of images to generate (1-10).

        Returns:
            ImageResult with generated image URLs or base64 data.
        """
        payload: dict[str, Any] = {"prompt": prompt}
        if size is not None:
            payload["size"] = size
        if n is not None:
            payload["n"] = n

        data = await self._request("POST", "/images/generations", json=payload)

        images = [
            ImageData(
                url=img.get("url"),
                b64_json=img.get("b64_json"),
                revised_prompt=img.get("revised_prompt"),
            )
            for img in data.get("data", [])
        ]

        return ImageResult(
            created=data.get("created", 0),
            data=images,
        )

    @action("Transcribe audio to text")
    async def transcribe_audio(
        self,
        file_url: str,
        model: Optional[str] = None,
    ) -> AudioTranscription:
        """Transcribe audio from a URL using Whisper.

        Downloads the audio file from the provided URL and sends it
        to the OpenAI transcription API.

        Args:
            file_url: URL of the audio file to transcribe.
            model: Model to use for transcription (default: 'whisper-1').

        Returns:
            AudioTranscription with the transcribed text.
        """
        whisper_model = model or "whisper-1"

        # Download the audio file
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            audio_resp = await client.get(file_url)
            audio_resp.raise_for_status()
            audio_bytes = audio_resp.content

        # Determine filename from URL
        filename = file_url.split("/")[-1].split("?")[0] or "audio.mp3"

        # Send to transcription endpoint as multipart form data
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/audio/transcriptions",
                headers={"Authorization": f"Bearer {self._credentials}"},
                files={"file": (filename, audio_bytes)},
                data={"model": whisper_model, "response_format": "verbose_json"},
            )
            response.raise_for_status()
            data = response.json()

        return AudioTranscription(
            text=data.get("text", ""),
            language=data.get("language"),
            duration=data.get("duration"),
            segments=data.get("segments"),
        )

    @action("List assistants", idempotent=True)
    async def list_assistants(
        self,
        limit: Optional[int] = None,
    ) -> PaginatedList[Assistant]:
        """List all assistants associated with the account.

        Args:
            limit: Maximum number of assistants to return (1-100).

        Returns:
            Paginated list of Assistant objects.
        """
        params: dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit

        headers = self._get_headers()
        headers["OpenAI-Beta"] = "assistants=v2"

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(
                f"{self._base_url}/assistants",
                headers=headers,
                params=params,
            )
            response.raise_for_status()
            data = response.json()

        assistants = [
            Assistant(
                id=a.get("id", ""),
                object=a.get("object", "assistant"),
                created_at=a.get("created_at", 0),
                name=a.get("name"),
                description=a.get("description"),
                model=a.get("model", ""),
                instructions=a.get("instructions"),
                tools=[
                    ToolDefinition(type=t.get("type", ""))
                    for t in a.get("tools", [])
                ],
                metadata=a.get("metadata", {}),
            )
            for a in data.get("data", [])
        ]

        return PaginatedList(
            items=assistants,
            page_state=PageState(
                cursor=data.get("last_id"),
                has_more=data.get("has_more", False),
            ),
        )

    @action("Create an assistant")
    async def create_assistant(
        self,
        model: str,
        name: str,
        instructions: Optional[str] = None,
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> Assistant:
        """Create a new assistant with the specified configuration.

        Args:
            model: Model ID for the assistant (e.g., 'gpt-4o').
            name: Name for the assistant.
            instructions: System instructions for the assistant.
            tools: List of tool definitions (e.g., [{"type": "code_interpreter"}]).

        Returns:
            The created Assistant object.
        """
        payload: dict[str, Any] = {
            "model": model,
            "name": name,
        }
        if instructions is not None:
            payload["instructions"] = instructions
        if tools is not None:
            payload["tools"] = tools

        headers = self._get_headers()
        headers["OpenAI-Beta"] = "assistants=v2"

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/assistants",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        return Assistant(
            id=data.get("id", ""),
            object=data.get("object", "assistant"),
            created_at=data.get("created_at", 0),
            name=data.get("name"),
            description=data.get("description"),
            model=data.get("model", ""),
            instructions=data.get("instructions"),
            tools=[
                ToolDefinition(type=t.get("type", ""))
                for t in data.get("tools", [])
            ],
            metadata=data.get("metadata", {}),
        )

    @action("List uploaded files", idempotent=True)
    async def list_files(
        self,
        purpose: Optional[str] = None,
    ) -> list[OpenAIFile]:
        """List files uploaded to the OpenAI platform.

        Args:
            purpose: Filter by purpose (e.g., 'assistants', 'fine-tune', 'batch').

        Returns:
            List of OpenAIFile objects with file metadata.
        """
        params: dict[str, Any] = {}
        if purpose is not None:
            params["purpose"] = purpose

        data = await self._request("GET", "/files", params=params)

        return [
            OpenAIFile(
                id=f.get("id", ""),
                object=f.get("object", "file"),
                bytes=f.get("bytes", 0),
                created_at=f.get("created_at", 0),
                filename=f.get("filename", ""),
                purpose=f.get("purpose", ""),
                status=f.get("status"),
            )
            for f in data.get("data", [])
        ]
