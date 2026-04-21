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
    ChatChoice,
    ChatCompletion,
    ChatMessage,
    Embedding,
    EmbeddingData,
    FineTuningJob,
    ImageData,
    ImageResult,
    ModerationResult,
    OpenAIFile,
    OpenAIModel,
    Thread,
    ThreadMessage,
    ThreadMessageContent,
    ThreadRun,
    ThreadRunUsage,
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
                tools=[ToolDefinition(type=t.get("type", "")) for t in a.get("tools", [])],
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
            tools=[ToolDefinition(type=t.get("type", "")) for t in data.get("tools", [])],
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

    # ------------------------------------------------------------------
    # Actions -- Models (extended)
    # ------------------------------------------------------------------

    @action("Get a model by ID", idempotent=True)
    async def get_model(self, model_id: str) -> OpenAIModel:
        """Retrieve details about a specific model.

        Args:
            model_id: The model identifier (e.g., ``'gpt-4o'``).

        Returns:
            OpenAIModel with model metadata.
        """
        data = await self._request("GET", f"/models/{model_id}")

        return OpenAIModel(
            id=data.get("id", ""),
            object=data.get("object", "model"),
            created=data.get("created", 0),
            owned_by=data.get("owned_by", ""),
        )

    @action("Delete a fine-tuned model", dangerous=True)
    async def delete_model(self, model_id: str) -> bool:
        """Delete a fine-tuned model.

        Only the owner of a fine-tuned model can delete it.

        Args:
            model_id: The model ID to delete (must be a fine-tuned model).

        Returns:
            True if the model was successfully deleted.
        """
        data = await self._request("DELETE", f"/models/{model_id}")
        return data.get("deleted", False)

    # ------------------------------------------------------------------
    # Actions -- Fine-tuning
    # ------------------------------------------------------------------

    @action("Create a fine-tuning job", dangerous=True)
    async def create_fine_tuning_job(
        self,
        model: str,
        training_file: str,
    ) -> FineTuningJob:
        """Create a new fine-tuning job.

        Args:
            model: The base model to fine-tune (e.g. ``"gpt-4o-mini-2024-07-18"``).
            training_file: The file ID of the uploaded training data.

        Returns:
            The created FineTuningJob.
        """
        payload: dict[str, Any] = {
            "model": model,
            "training_file": training_file,
        }
        data = await self._request("POST", "/fine_tuning/jobs", json=payload)
        return FineTuningJob(
            id=data.get("id", ""),
            object=data.get("object", "fine_tuning.job"),
            model=data.get("model", ""),
            training_file=data.get("training_file", ""),
            status=data.get("status"),
            created_at=data.get("created_at", 0),
            finished_at=data.get("finished_at"),
            fine_tuned_model=data.get("fine_tuned_model"),
            error=data.get("error"),
        )

    @action("List fine-tuning jobs", idempotent=True)
    async def list_fine_tuning_jobs(
        self,
        limit: Optional[int] = None,
    ) -> list[FineTuningJob]:
        """List fine-tuning jobs.

        Args:
            limit: Maximum number of jobs to return.

        Returns:
            List of FineTuningJob objects.
        """
        params: dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit

        data = await self._request(
            "GET",
            "/fine_tuning/jobs",
            params=params or None,
        )
        return [
            FineTuningJob(
                id=j.get("id", ""),
                object=j.get("object", "fine_tuning.job"),
                model=j.get("model", ""),
                training_file=j.get("training_file", ""),
                status=j.get("status"),
                created_at=j.get("created_at", 0),
                finished_at=j.get("finished_at"),
                fine_tuned_model=j.get("fine_tuned_model"),
                error=j.get("error"),
            )
            for j in data.get("data", [])
        ]

    # ------------------------------------------------------------------
    # Actions -- File management (extended)
    # ------------------------------------------------------------------

    @action("Upload a file to OpenAI")
    async def upload_file(
        self,
        file_content: bytes,
        purpose: str,
        filename: Optional[str] = None,
    ) -> OpenAIFile:
        """Upload a file to the OpenAI platform.

        Args:
            file_content: Raw file bytes to upload.
            purpose: Intended purpose (``'assistants'``, ``'fine-tune'``,
                ``'batch'``, ``'vision'``).
            filename: Name for the uploaded file (default: ``"upload.jsonl"``).

        Returns:
            The created OpenAIFile with file metadata.
        """
        upload_name = filename or "upload.jsonl"

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/files",
                headers={"Authorization": f"Bearer {self._credentials}"},
                files={"file": (upload_name, file_content)},
                data={"purpose": purpose},
            )
            response.raise_for_status()
            data = response.json()

        return OpenAIFile(
            id=data.get("id", ""),
            object=data.get("object", "file"),
            bytes=data.get("bytes", 0),
            created_at=data.get("created_at", 0),
            filename=data.get("filename", ""),
            purpose=data.get("purpose", ""),
            status=data.get("status"),
        )

    @action("Get file metadata by ID", idempotent=True)
    async def get_file(self, file_id: str) -> OpenAIFile:
        """Retrieve metadata for an uploaded file.

        Args:
            file_id: The file ID to retrieve.

        Returns:
            OpenAIFile with file metadata.
        """
        data = await self._request("GET", f"/files/{file_id}")

        return OpenAIFile(
            id=data.get("id", ""),
            object=data.get("object", "file"),
            bytes=data.get("bytes", 0),
            created_at=data.get("created_at", 0),
            filename=data.get("filename", ""),
            purpose=data.get("purpose", ""),
            status=data.get("status"),
        )

    @action("Get file content by ID", idempotent=True)
    async def get_file_content(self, file_id: str) -> str:
        """Retrieve the content of an uploaded file.

        Args:
            file_id: The file ID whose content to retrieve.

        Returns:
            The file content as a string.
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(
                f"{self._base_url}/files/{file_id}/content",
                headers=self._get_headers(),
            )
            response.raise_for_status()
            return response.text

    @action("Delete an uploaded file", dangerous=True)
    async def delete_file(self, file_id: str) -> bool:
        """Delete a file from OpenAI.

        Args:
            file_id: The file ID to delete.

        Returns:
            True if the file was deleted.
        """
        data = await self._request("DELETE", f"/files/{file_id}")
        return data.get("deleted", False)

    # ------------------------------------------------------------------
    # Actions -- Moderation
    # ------------------------------------------------------------------

    @action("Run content moderation on text")
    async def create_moderation(self, input: str) -> ModerationResult:
        """Check if text violates OpenAI content policy.

        Args:
            input: The text to moderate.

        Returns:
            ModerationResult with categories and scores.
        """
        data = await self._request(
            "POST",
            "/moderations",
            json={"input": input},
        )
        results = data.get("results", [{}])
        r = results[0] if results else {}
        return ModerationResult(
            id=data.get("id", ""),
            model=data.get("model", ""),
            flagged=r.get("flagged", False),
            categories=r.get("categories", {}),
            category_scores=r.get("category_scores", {}),
        )

    # ------------------------------------------------------------------
    # Actions -- Assistants (extended)
    # ------------------------------------------------------------------

    @action("Get an assistant by ID", idempotent=True)
    async def get_assistant(self, assistant_id: str) -> Assistant:
        """Retrieve an assistant by its ID.

        Args:
            assistant_id: The assistant ID to retrieve.

        Returns:
            The Assistant object with full configuration.
        """
        headers = self._get_headers()
        headers["OpenAI-Beta"] = "assistants=v2"

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(
                f"{self._base_url}/assistants/{assistant_id}",
                headers=headers,
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
            tools=[ToolDefinition(type=t.get("type", "")) for t in data.get("tools", [])],
            metadata=data.get("metadata", {}),
        )

    @action("Update an assistant")
    async def update_assistant(
        self,
        assistant_id: str,
        name: Optional[str] = None,
        instructions: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Assistant:
        """Modify an existing assistant's configuration.

        Args:
            assistant_id: The assistant ID to update.
            name: New name for the assistant.
            instructions: New system instructions.
            model: New model ID for the assistant.

        Returns:
            The updated Assistant object.
        """
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if instructions is not None:
            payload["instructions"] = instructions
        if model is not None:
            payload["model"] = model

        headers = self._get_headers()
        headers["OpenAI-Beta"] = "assistants=v2"

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/assistants/{assistant_id}",
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
            tools=[ToolDefinition(type=t.get("type", "")) for t in data.get("tools", [])],
            metadata=data.get("metadata", {}),
        )

    @action("Delete an assistant", dangerous=True)
    async def delete_assistant(self, assistant_id: str) -> bool:
        """Permanently delete an assistant.

        Args:
            assistant_id: The assistant ID to delete.

        Returns:
            True if the assistant was successfully deleted.
        """
        headers = self._get_headers()
        headers["OpenAI-Beta"] = "assistants=v2"

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.delete(
                f"{self._base_url}/assistants/{assistant_id}",
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

        return data.get("deleted", False)

    # ------------------------------------------------------------------
    # Actions -- Threads
    # ------------------------------------------------------------------

    @action("Create a thread")
    async def create_thread(self) -> Thread:
        """Create a new conversation thread for use with assistants.

        Returns:
            The created Thread object.
        """
        headers = self._get_headers()
        headers["OpenAI-Beta"] = "assistants=v2"

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/threads",
                headers=headers,
                json={},
            )
            response.raise_for_status()
            data = response.json()

        return Thread(
            id=data.get("id", ""),
            object=data.get("object", "thread"),
            created_at=data.get("created_at", 0),
            metadata=data.get("metadata", {}),
        )

    @action("Create a message in a thread")
    async def create_thread_message(
        self,
        thread_id: str,
        content: str,
        role: Optional[str] = None,
    ) -> ThreadMessage:
        """Add a message to an existing thread.

        Args:
            thread_id: The thread ID to add the message to.
            content: The text content of the message.
            role: The role of the message author (``'user'`` or ``'assistant'``).
                Defaults to ``'user'``.

        Returns:
            The created ThreadMessage.
        """
        payload: dict[str, Any] = {
            "role": role or "user",
            "content": content,
        }

        headers = self._get_headers()
        headers["OpenAI-Beta"] = "assistants=v2"

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/threads/{thread_id}/messages",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        content_blocks = [
            ThreadMessageContent(
                type=c.get("type", "text"),
                text=c.get("text"),
            )
            for c in data.get("content", [])
        ]

        return ThreadMessage(
            id=data.get("id", ""),
            object=data.get("object", "thread.message"),
            created_at=data.get("created_at", 0),
            thread_id=data.get("thread_id", ""),
            role=data.get("role", "user"),
            content=content_blocks,
            assistant_id=data.get("assistant_id"),
            run_id=data.get("run_id"),
            metadata=data.get("metadata", {}),
        )

    @action("Run a thread with an assistant")
    async def run_thread(
        self,
        thread_id: str,
        assistant_id: str,
    ) -> ThreadRun:
        """Create a run to execute an assistant on a thread.

        Args:
            thread_id: The thread ID to run.
            assistant_id: The assistant ID to execute.

        Returns:
            The created ThreadRun with initial status.
        """
        payload: dict[str, Any] = {
            "assistant_id": assistant_id,
        }

        headers = self._get_headers()
        headers["OpenAI-Beta"] = "assistants=v2"

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/threads/{thread_id}/runs",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        usage_data = data.get("usage")
        usage = (
            ThreadRunUsage(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
            )
            if usage_data
            else None
        )

        return ThreadRun(
            id=data.get("id", ""),
            object=data.get("object", "thread.run"),
            created_at=data.get("created_at", 0),
            thread_id=data.get("thread_id", ""),
            assistant_id=data.get("assistant_id", ""),
            status=data.get("status", "queued"),
            model=data.get("model", ""),
            instructions=data.get("instructions"),
            tools=[ToolDefinition(type=t.get("type", "")) for t in data.get("tools", [])],
            usage=usage,
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            failed_at=data.get("failed_at"),
            metadata=data.get("metadata", {}),
        )

    @action("Get a thread run by ID", idempotent=True)
    async def get_thread_run(
        self,
        thread_id: str,
        run_id: str,
    ) -> ThreadRun:
        """Retrieve a run to check its status and results.

        Can be used to poll for run completion.

        Args:
            thread_id: The thread ID the run belongs to.
            run_id: The run ID to retrieve.

        Returns:
            ThreadRun with current status and usage stats.
        """
        headers = self._get_headers()
        headers["OpenAI-Beta"] = "assistants=v2"

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(
                f"{self._base_url}/threads/{thread_id}/runs/{run_id}",
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

        usage_data = data.get("usage")
        usage = (
            ThreadRunUsage(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
            )
            if usage_data
            else None
        )

        return ThreadRun(
            id=data.get("id", ""),
            object=data.get("object", "thread.run"),
            created_at=data.get("created_at", 0),
            thread_id=data.get("thread_id", ""),
            assistant_id=data.get("assistant_id", ""),
            status=data.get("status", "queued"),
            model=data.get("model", ""),
            instructions=data.get("instructions"),
            tools=[ToolDefinition(type=t.get("type", "")) for t in data.get("tools", [])],
            usage=usage,
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            failed_at=data.get("failed_at"),
            metadata=data.get("metadata", {}),
        )

    @action("List messages in a thread", idempotent=True)
    async def list_thread_messages(
        self,
        thread_id: str,
        limit: Optional[int] = None,
    ) -> list[ThreadMessage]:
        """List all messages in a thread.

        Args:
            thread_id: The thread ID to list messages from.
            limit: Maximum number of messages to return (1-100).

        Returns:
            List of ThreadMessage objects in the thread.
        """
        params: dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit

        headers = self._get_headers()
        headers["OpenAI-Beta"] = "assistants=v2"

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(
                f"{self._base_url}/threads/{thread_id}/messages",
                headers=headers,
                params=params,
            )
            response.raise_for_status()
            data = response.json()

        messages: list[ThreadMessage] = []
        for m in data.get("data", []):
            content_blocks = [
                ThreadMessageContent(
                    type=c.get("type", "text"),
                    text=c.get("text"),
                )
                for c in m.get("content", [])
            ]
            messages.append(
                ThreadMessage(
                    id=m.get("id", ""),
                    object=m.get("object", "thread.message"),
                    created_at=m.get("created_at", 0),
                    thread_id=m.get("thread_id", ""),
                    role=m.get("role", "user"),
                    content=content_blocks,
                    assistant_id=m.get("assistant_id"),
                    run_id=m.get("run_id"),
                    metadata=m.get("metadata", {}),
                )
            )
        return messages

    # ------------------------------------------------------------------
    # Actions -- Audio (extended)
    # ------------------------------------------------------------------

    @action("Generate speech audio from text")
    async def create_speech(
        self,
        input: str,
        voice: str,
        model: Optional[str] = None,
        response_format: Optional[str] = None,
        speed: Optional[float] = None,
    ) -> bytes:
        """Generate speech audio from text using a TTS model.

        Args:
            input: The text to synthesize into speech (max 4096 chars).
            voice: Voice to use (``'alloy'``, ``'ash'``, ``'coral'``,
                ``'echo'``, ``'fable'``, ``'onyx'``, ``'nova'``,
                ``'sage'``, ``'shimmer'``).
            model: TTS model (``'tts-1'``, ``'tts-1-hd'``,
                ``'gpt-4o-mini-tts'``). Defaults to ``'tts-1'``.
            response_format: Audio format (``'mp3'``, ``'opus'``,
                ``'aac'``, ``'flac'``, ``'wav'``, ``'pcm'``).
            speed: Playback speed from 0.25 to 4.0 (default 1.0).

        Returns:
            Raw audio bytes in the specified format.
        """
        payload: dict[str, Any] = {
            "model": model or "tts-1",
            "input": input,
            "voice": voice,
        }
        if response_format is not None:
            payload["response_format"] = response_format
        if speed is not None:
            payload["speed"] = speed

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/audio/speech",
                headers=self._get_headers(),
                json=payload,
            )
            response.raise_for_status()
            return response.content
