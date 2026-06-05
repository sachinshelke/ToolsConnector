"""Groq connector -- ultra-fast chat, models, audio, speech, files, and batches.

Groq serves open models (Llama, Whisper, PlayAI TTS, ...) behind an
OpenAI-compatible REST API. This connector uses httpx for direct HTTP
calls against that API and expects a Bearer API key passed as
``credentials`` (BYOK). It covers chat completions, model discovery,
Whisper transcription/translation, text-to-speech, file management, and
the asynchronous Batch API.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional, Union

import httpx

from toolsconnector.connectors._helpers import raise_typed_for_status
from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import (
    ConnectorCategory,
    ProtocolType,
    RateLimitSpec,
)

from .types import (
    AudioTranscription,
    Batch,
    BatchRequestCounts,
    ChatChoice,
    ChatCompletion,
    ChatMessage,
    GroqFile,
    GroqModel,
    Usage,
)

logger = logging.getLogger("toolsconnector.groq")


class Groq(BaseConnector):
    """Connect to Groq for fast chat completions, model listing, and audio.

    Supports Bearer token authentication. Pass an API key as
    ``credentials`` when instantiating. Uses the OpenAI-compatible
    Groq REST API (``/openai/v1``) via direct httpx calls.
    """

    name = "groq"
    display_name = "Groq"
    category = ConnectorCategory.AI_ML
    protocol = ProtocolType.REST
    base_url = "https://api.groq.com/openai/v1"
    description = (
        "Connect to Groq for ultra-low-latency chat completions on open "
        "models (Llama, Mixtral), model discovery, Whisper audio "
        "transcription and translation, PlayAI text-to-speech, file "
        "management, and the asynchronous Batch API."
    )
    verification_status = "pattern"
    _rate_limit_config = RateLimitSpec(rate=60, period=60, burst=20)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_headers(self) -> dict[str, str]:
        """Build authorization headers for Groq API requests.

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
        """Execute an authenticated HTTP request against the Groq API.

        Args:
            method: HTTP method (GET, POST, DELETE, etc.).
            path: API path relative to base_url.
            **kwargs: Additional keyword arguments passed to httpx.

        Returns:
            Parsed JSON response as a dict.

        Raises:
            toolsconnector.errors.APIError (subclass): On any non-2xx response.
                Maps to a typed exception by status: 401 -> InvalidCredentialsError
                or TokenExpiredError; 403 -> PermissionDeniedError; 404 -> NotFoundError;
                409 -> ConflictError; 400/422 -> ValidationError; 429 -> RateLimitError;
                5xx -> ServerError; other 4xx -> APIError. See
                toolsconnector.connectors._helpers.raise_typed_for_status for the full mapping.

        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.request(
                method,
                f"{self._base_url}{path}",
                headers=self._get_headers(),
                **kwargs,
            )
            raise_typed_for_status(response, connector=self.name)
            if response.status_code == 204 or not response.content:
                return {}
            return response.json()

    async def _resolve_file(
        self,
        file_url_or_bytes: Union[str, bytes],
    ) -> tuple[str, bytes]:
        """Resolve an audio file argument into a ``(filename, content)`` pair.

        Mirrors the OpenAI connector's approach but accepts more inputs so
        either traditional apps or agents can pass whatever they have:

        - ``bytes``: used directly with a generic filename.
        - an ``http(s)://`` URL string: downloaded over httpx.
        - any other string: treated as a local filesystem path and read.

        Args:
            file_url_or_bytes: Raw audio bytes, an http(s) URL, or a local
                file path pointing at the audio to process.

        Returns:
            A tuple of ``(filename, content_bytes)`` for the multipart form.
        """
        if isinstance(file_url_or_bytes, bytes):
            return "audio.mp3", file_url_or_bytes

        if file_url_or_bytes.startswith(("http://", "https://")):
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                audio_resp = await client.get(file_url_or_bytes)
                raise_typed_for_status(audio_resp, connector=self.name)
                audio_bytes = audio_resp.content
            filename = file_url_or_bytes.split("/")[-1].split("?")[0] or "audio.mp3"
            return filename, audio_bytes

        # Local filesystem path.
        path = Path(file_url_or_bytes)
        return (path.name or "audio.mp3"), path.read_bytes()

    # ------------------------------------------------------------------
    # Actions -- Chat
    # ------------------------------------------------------------------

    @action("Create a chat completion")
    async def chat_completion(
        self,
        model: str,
        messages: list[dict[str, Any]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
    ) -> ChatCompletion:
        """Create a chat completion using the specified Groq model.

        Args:
            model: Model ID to use (e.g., 'llama-3.3-70b-versatile',
                'llama-3.1-8b-instant').
            messages: List of message dicts with 'role' and 'content' keys.
            temperature: Sampling temperature between 0 and 2.
            max_tokens: Maximum number of tokens to generate.
            top_p: Nucleus sampling probability mass between 0 and 1.

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
        if top_p is not None:
            payload["top_p"] = top_p

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

    # ------------------------------------------------------------------
    # Actions -- Models
    # ------------------------------------------------------------------

    @action("List available models", idempotent=True)
    async def list_models(self) -> list[GroqModel]:
        """List all models available to the authenticated account.

        Returns:
            List of GroqModel objects with model metadata.
        """
        data = await self._request("GET", "/models")

        return [
            GroqModel(
                id=m.get("id", ""),
                object=m.get("object", "model"),
                created=m.get("created", 0),
                owned_by=m.get("owned_by", ""),
                active=m.get("active"),
                context_window=m.get("context_window"),
            )
            for m in data.get("data", [])
        ]

    @action("Get a model by ID", idempotent=True)
    async def get_model(self, model: str) -> GroqModel:
        """Retrieve details about a specific model.

        Args:
            model: The model identifier (e.g., 'llama-3.3-70b-versatile').

        Returns:
            GroqModel with model metadata.
        """
        data = await self._request("GET", f"/models/{model}")

        return GroqModel(
            id=data.get("id", ""),
            object=data.get("object", "model"),
            created=data.get("created", 0),
            owned_by=data.get("owned_by", ""),
            active=data.get("active"),
            context_window=data.get("context_window"),
        )

    # ------------------------------------------------------------------
    # Actions -- Audio
    # ------------------------------------------------------------------

    @action("Transcribe audio to text")
    async def transcribe_audio(
        self,
        model: str,
        file_url_or_bytes: Union[str, bytes],
        language: Optional[str] = None,
        response_format: Optional[str] = None,
    ) -> AudioTranscription:
        """Transcribe audio to text in its original language.

        Accepts the audio as raw bytes, an http(s) URL (downloaded first),
        or a local file path, then sends it to the Groq transcription API
        as multipart form data.

        Args:
            model: Transcription model to use (e.g., 'whisper-large-v3').
            file_url_or_bytes: Raw audio bytes, an http(s) URL, or a local
                file path pointing at the audio to transcribe.
            language: ISO-639-1 language code of the source audio (e.g. 'en').
            response_format: Response format ('json', 'verbose_json', 'text').

        Returns:
            AudioTranscription with the transcribed text.
        """
        return await self._audio_request(
            "/audio/transcriptions",
            model=model,
            file_url_or_bytes=file_url_or_bytes,
            language=language,
            response_format=response_format,
        )

    @action("Translate audio to English text")
    async def translate_audio(
        self,
        model: str,
        file_url_or_bytes: Union[str, bytes],
        response_format: Optional[str] = None,
    ) -> AudioTranscription:
        """Translate audio in any supported language into English text.

        Accepts the audio as raw bytes, an http(s) URL (downloaded first),
        or a local file path, then sends it to the Groq translation API
        as multipart form data.

        Args:
            model: Translation model to use (e.g., 'whisper-large-v3').
            file_url_or_bytes: Raw audio bytes, an http(s) URL, or a local
                file path pointing at the audio to translate.
            response_format: Response format ('json', 'verbose_json', 'text').

        Returns:
            AudioTranscription with the translated English text.
        """
        return await self._audio_request(
            "/audio/translations",
            model=model,
            file_url_or_bytes=file_url_or_bytes,
            language=None,
            response_format=response_format,
        )

    async def _audio_request(
        self,
        path: str,
        *,
        model: str,
        file_url_or_bytes: Union[str, bytes],
        language: Optional[str],
        response_format: Optional[str],
    ) -> AudioTranscription:
        """Send a multipart audio request and parse the transcription result.

        Args:
            path: API path for the audio endpoint (transcription/translation).
            model: Model ID to use for the request.
            file_url_or_bytes: Raw audio bytes, an http(s) URL, or local path.
            language: Optional source language code (transcription only).
            response_format: Optional response format requested from the API.

        Returns:
            AudioTranscription parsed from the API response.
        """
        filename, audio_bytes = await self._resolve_file(file_url_or_bytes)

        form: dict[str, str] = {"model": model}
        if language is not None:
            form["language"] = language
        if response_format is not None:
            form["response_format"] = response_format

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}{path}",
                headers={"Authorization": f"Bearer {self._credentials}"},
                files={"file": (filename, audio_bytes)},
                data=form,
            )
            raise_typed_for_status(response, connector=self.name)
            data = response.json()

        return AudioTranscription(
            text=data.get("text", ""),
            language=data.get("language"),
            duration=data.get("duration"),
            segments=data.get("segments"),
        )

    @action("Generate speech audio from text")
    async def create_speech(
        self,
        model: str,
        input: str,
        voice: str,
        response_format: Optional[str] = None,
        sample_rate: Optional[int] = None,
        speed: Optional[float] = None,
    ) -> bytes:
        """Synthesize speech audio from text using a Groq TTS model.

        Sends a JSON request to ``POST /audio/speech`` and returns the raw
        audio bytes in the requested format (``mp3`` by default). Use a
        PlayAI text-to-speech model and voice, for example ``model``
        ``'playai-tts'`` with ``voice`` ``'Fritz-PlayAI'``.

        Args:
            model: TTS model ID to use (e.g. ``'playai-tts'``,
                ``'playai-tts-arabic'``).
            input: The text to synthesize into speech.
            voice: Voice to speak with (e.g. ``'Fritz-PlayAI'``,
                ``'Arista-PlayAI'``).
            response_format: Audio format to return (``'mp3'``, ``'wav'``,
                ``'flac'``, ``'ogg'``, ``'mulaw'``). Defaults to ``'mp3'``.
            sample_rate: Output sample rate in Hz (one of 8000, 16000,
                22050, 24000, 32000, 44100, 48000). Defaults to 48000.
            speed: Playback speed multiplier between 0.5 and 5.0
                (default 1.0).

        Returns:
            Raw audio bytes in the requested ``response_format``.
        """
        payload: dict[str, Any] = {
            "model": model,
            "input": input,
            "voice": voice,
        }
        if response_format is not None:
            payload["response_format"] = response_format
        if sample_rate is not None:
            payload["sample_rate"] = sample_rate
        if speed is not None:
            payload["speed"] = speed

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/audio/speech",
                headers=self._get_headers(),
                json=payload,
            )
            raise_typed_for_status(response, connector=self.name)
            return response.content

    # ------------------------------------------------------------------
    # Internal parsers -- Files / Batches
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_file(data: dict[str, Any]) -> GroqFile:
        """Build a :class:`GroqFile` from a raw file object dict.

        Args:
            data: Raw JSON file object from the Files API.

        Returns:
            The parsed GroqFile model.
        """
        return GroqFile(
            id=data.get("id", ""),
            object=data.get("object", "file"),
            bytes=data.get("bytes", 0),
            created_at=data.get("created_at", 0),
            filename=data.get("filename", ""),
            purpose=data.get("purpose", ""),
        )

    @staticmethod
    def _parse_batch(data: dict[str, Any]) -> Batch:
        """Build a :class:`Batch` from a raw batch object dict.

        Args:
            data: Raw JSON batch object from the Batch API.

        Returns:
            The parsed Batch model, including request counts when present.
        """
        counts_data = data.get("request_counts")
        request_counts = (
            BatchRequestCounts(
                total=counts_data.get("total", 0),
                completed=counts_data.get("completed", 0),
                failed=counts_data.get("failed", 0),
            )
            if counts_data
            else None
        )

        return Batch(
            id=data.get("id", ""),
            object=data.get("object", "batch"),
            endpoint=data.get("endpoint", ""),
            input_file_id=data.get("input_file_id", ""),
            completion_window=data.get("completion_window", ""),
            status=data.get("status", ""),
            output_file_id=data.get("output_file_id"),
            error_file_id=data.get("error_file_id"),
            errors=data.get("errors"),
            request_counts=request_counts,
            created_at=data.get("created_at", 0),
            in_progress_at=data.get("in_progress_at"),
            expires_at=data.get("expires_at"),
            finalizing_at=data.get("finalizing_at"),
            completed_at=data.get("completed_at"),
            failed_at=data.get("failed_at"),
            expired_at=data.get("expired_at"),
            cancelling_at=data.get("cancelling_at"),
            cancelled_at=data.get("cancelled_at"),
            metadata=data.get("metadata"),
        )

    # ------------------------------------------------------------------
    # Actions -- Files
    # ------------------------------------------------------------------

    @action("Upload a file to Groq")
    async def upload_file(
        self,
        file_content: bytes,
        purpose: str = "batch",
        filename: Optional[str] = None,
    ) -> GroqFile:
        """Upload a file to Groq for use with the Batch API.

        Sends multipart form data to ``POST /files``. Batch input files
        must be JSONL where each line is a request matching the target
        endpoint's schema.

        Args:
            file_content: Raw file bytes to upload (typically JSONL).
            purpose: Intended purpose of the file. Use ``'batch'`` for
                batch input (the default) or ``'batch_output'``.
            filename: Name for the uploaded file (default
                ``"batch.jsonl"``).

        Returns:
            The created GroqFile with file metadata.
        """
        upload_name = filename or "batch.jsonl"

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/files",
                headers={"Authorization": f"Bearer {self._credentials}"},
                files={"file": (upload_name, file_content)},
                data={"purpose": purpose},
            )
            raise_typed_for_status(response, connector=self.name)
            data = response.json()

        return self._parse_file(data)

    @action("List uploaded files", idempotent=True)
    async def list_files(
        self,
        purpose: Optional[str] = None,
    ) -> list[GroqFile]:
        """List files uploaded to the Groq platform.

        Args:
            purpose: Optional filter restricting results to a single
                purpose (e.g. ``'batch'``).

        Returns:
            List of GroqFile objects from the ``data`` array.
        """
        params: dict[str, Any] = {}
        if purpose is not None:
            params["purpose"] = purpose

        data = await self._request("GET", "/files", params=params or None)

        return [self._parse_file(f) for f in data.get("data", [])]

    @action("Get file metadata by ID", idempotent=True)
    async def get_file(self, file_id: str) -> GroqFile:
        """Retrieve metadata for an uploaded file.

        Args:
            file_id: The file ID to retrieve (e.g. ``'file_01...'``).

        Returns:
            GroqFile with file metadata.
        """
        data = await self._request("GET", f"/files/{file_id}")
        return self._parse_file(data)

    @action("Get file content by ID", idempotent=True)
    async def get_file_content(self, file_id: str) -> bytes:
        """Download the raw content of an uploaded file.

        Useful for retrieving a batch's output or error file once the
        batch has completed.

        Args:
            file_id: The file ID whose content to download.

        Returns:
            The file content as raw bytes (typically JSONL).
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(
                f"{self._base_url}/files/{file_id}/content",
                headers=self._get_headers(),
            )
            raise_typed_for_status(response, connector=self.name)
            return response.content

    @action("Delete an uploaded file", dangerous=True)
    async def delete_file(self, file_id: str) -> bool:
        """Delete a file from the Groq platform.

        Args:
            file_id: The file ID to delete.

        Returns:
            True if the file was successfully deleted.
        """
        data = await self._request("DELETE", f"/files/{file_id}")
        return data.get("deleted", False)

    # ------------------------------------------------------------------
    # Actions -- Batches
    # ------------------------------------------------------------------

    @action("Create a batch job")
    async def create_batch(
        self,
        input_file_id: str,
        endpoint: str,
        completion_window: str = "24h",
        metadata: Optional[dict[str, Any]] = None,
    ) -> Batch:
        """Create an asynchronous batch job over an uploaded JSONL file.

        Sends a JSON request to ``POST /batches``. The ``input_file_id``
        must reference a file uploaded with purpose ``'batch'``.

        Args:
            input_file_id: ID of the uploaded JSONL input file.
            endpoint: Target endpoint each line runs against. One of
                ``'/v1/chat/completions'``, ``'/v1/audio/transcriptions'``,
                or ``'/v1/audio/translations'``.
            completion_window: Time window in which to finish the batch
                (``'24h'`` through ``'7d'``). Defaults to ``'24h'``.
            metadata: Optional custom key-value metadata for the batch.

        Returns:
            The created Batch with its initial status.
        """
        payload: dict[str, Any] = {
            "input_file_id": input_file_id,
            "endpoint": endpoint,
            "completion_window": completion_window,
        }
        if metadata is not None:
            payload["metadata"] = metadata

        data = await self._request("POST", "/batches", json=payload)
        return self._parse_batch(data)

    @action("List batch jobs", idempotent=True)
    async def list_batches(
        self,
        limit: Optional[int] = None,
    ) -> list[Batch]:
        """List batch jobs created by the authenticated account.

        Args:
            limit: Maximum number of batches to return.

        Returns:
            List of Batch objects from the ``data`` array.
        """
        params: dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit

        data = await self._request("GET", "/batches", params=params or None)

        return [self._parse_batch(b) for b in data.get("data", [])]

    @action("Get a batch job by ID", idempotent=True)
    async def get_batch(self, batch_id: str) -> Batch:
        """Retrieve a batch job to check its status and result files.

        Can be polled to await completion; once ``status`` is
        ``'completed'`` the ``output_file_id`` (and any ``error_file_id``)
        can be downloaded via :meth:`get_file_content`.

        Args:
            batch_id: The batch ID to retrieve (e.g. ``'batch_01...'``).

        Returns:
            Batch with current status, request counts, and file IDs.
        """
        data = await self._request("GET", f"/batches/{batch_id}")
        return self._parse_batch(data)

    @action("Cancel a batch job", dangerous=True)
    async def cancel_batch(self, batch_id: str) -> Batch:
        """Cancel an in-progress batch job.

        The batch moves to status ``'cancelling'`` and then ``'cancelled'``
        once any in-flight requests finish.

        Args:
            batch_id: The batch ID to cancel.

        Returns:
            The Batch reflecting its cancelling/cancelled status.
        """
        data = await self._request("POST", f"/batches/{batch_id}/cancel")
        return self._parse_batch(data)
