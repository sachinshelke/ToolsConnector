"""Google Gemini connector -- generation, embeddings, files, caching, and tuning.

Uses httpx for direct HTTP calls against the Gemini REST API (v1beta) at
``generativelanguage.googleapis.com``. Expects an API key passed as
``credentials`` (Bring Your Own Key).

The API key is sent in the ``x-goog-api-key`` request header rather than as a
URL query parameter, keeping secrets out of URLs and logs.

Coverage spans the documented surface: content generation and token counting,
single and batch embeddings, model discovery, the Files API (upload/get/list/
delete), context caching (``cachedContents``), and tuned models.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional, Union

import httpx

from toolsconnector.connectors._helpers import raise_typed_for_status
from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import (
    ConnectorCategory,
    ProtocolType,
    RateLimitSpec,
)

from ._parsers import (
    assemble_stream_result,
    parse_cached_content,
    parse_file,
    parse_generate_response,
    parse_model,
    parse_tuned_model,
)
from .types import (
    BatchEmbeddings,
    CachedContent,
    CachedContentList,
    Embedding,
    FileList,
    GeminiFile,
    GeminiModel,
    GeminiResponse,
    GeminiStreamResult,
    TokenCount,
    TunedModel,
    TunedModelList,
)

logger = logging.getLogger("toolsconnector.gemini")


class Gemini(BaseConnector):
    """Connect to Google Gemini for generation, embeddings, files, caching, and tuning.

    Supports API key authentication via the ``x-goog-api-key`` header. Pass an
    API key as ``credentials`` when instantiating. Uses the Gemini REST API
    (v1beta) via direct httpx calls.
    """

    name = "gemini"
    display_name = "Google Gemini"
    category = ConnectorCategory.AI_ML
    protocol = ProtocolType.REST
    base_url = "https://generativelanguage.googleapis.com/v1beta"
    description = (
        "Connect to Google Gemini for generating content with Gemini models, "
        "counting tokens, creating embeddings, managing uploaded files, context "
        "caches, and tuned models."
    )
    verification_status = "live"
    _rate_limit_config = RateLimitSpec(rate=60, period=60, burst=20)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_headers(self) -> dict[str, str]:
        """Build authentication headers for Gemini API requests.

        The API key travels in the ``x-goog-api-key`` header so it never
        appears in a URL query string (and thus never in server logs).

        Returns:
            Dict with the x-goog-api-key and content-type headers.
        """
        return {
            "x-goog-api-key": str(self._credentials),
            "Content-Type": "application/json",
        }

    def _upload_base(self) -> str:
        """Return the media-upload base URL for the Files API.

        File uploads use the resumable upload endpoint at ``/upload/v1beta``
        rather than the regular ``/v1beta`` path, so the trailing API-version
        segment is rewritten with the ``upload/`` prefix.

        Returns:
            The base URL ending in ``/upload/v1beta``.
        """
        base = self._base_url or self.__class__.base_url
        if base.endswith("/v1beta"):
            return base[: -len("/v1beta")] + "/upload/v1beta"
        return base

    @staticmethod
    def _model_path(model: str) -> str:
        """Normalise a model identifier into a ``models/{id}`` path segment.

        Accepts a bare model id (``'gemini-2.0-flash'``), one already
        carrying the ``models/`` prefix, or a tuned model reference
        (``'tunedModels/{id}'``), and returns the canonical resource path.
        Tuned model references are passed through untouched so generation
        can target them.

        Args:
            model: The model id, with or without the ``models/`` prefix, or a
                ``tunedModels/{id}`` reference.

        Returns:
            The model reference as ``models/{id}`` (or the untouched tuned
            model path).
        """
        cleaned = model.strip()
        if cleaned.startswith(("models/", "tunedModels/")):
            return cleaned
        return f"models/{cleaned}"

    @staticmethod
    def _file_path(name: str) -> str:
        """Normalise a file identifier into a ``files/{id}`` path segment.

        Args:
            name: The file id, with or without the ``files/`` prefix.

        Returns:
            The file reference as ``files/{id}``.
        """
        cleaned = name.strip()
        if cleaned.startswith("files/"):
            return cleaned
        return f"files/{cleaned}"

    @staticmethod
    def _cache_path(name: str) -> str:
        """Normalise a cache identifier into a ``cachedContents/{id}`` segment.

        Args:
            name: The cache id, with or without the ``cachedContents/`` prefix.

        Returns:
            The cache reference as ``cachedContents/{id}``.
        """
        cleaned = name.strip()
        if cleaned.startswith("cachedContents/"):
            return cleaned
        return f"cachedContents/{cleaned}"

    @staticmethod
    def _tuned_model_path(name: str) -> str:
        """Normalise a tuned model identifier into a ``tunedModels/{id}`` segment.

        Args:
            name: The tuned model id, with or without the ``tunedModels/``
                prefix.

        Returns:
            The tuned model reference as ``tunedModels/{id}``.
        """
        cleaned = name.strip()
        if cleaned.startswith("tunedModels/"):
            return cleaned
        return f"tunedModels/{cleaned}"

    @staticmethod
    def _wrap_contents(contents: Union[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
        """Wrap a prompt string into a single content turn, or pass a list through.

        Args:
            contents: A plain prompt string or a pre-built list of content
                dicts with ``role`` and ``parts`` keys.

        Returns:
            A list of content dicts suitable for the request body.
        """
        if isinstance(contents, str):
            return [{"parts": [{"text": contents}]}]
        return contents

    def _build_generation_payload(
        self,
        *,
        contents: Union[str, list[dict[str, Any]]],
        system_instruction: Optional[str],
        temperature: Optional[float],
        max_output_tokens: Optional[int],
        tools: Optional[list[dict[str, Any]]],
        tool_config: Optional[dict[str, Any]],
        safety_settings: Optional[list[dict[str, Any]]],
        generation_config: Optional[dict[str, Any]],
        cached_content: Optional[str],
    ) -> dict[str, Any]:
        """Build the request body shared by generate / stream generate.

        ``temperature`` and ``max_output_tokens`` are conveniences folded
        into ``generationConfig``; any keys in the caller-supplied
        ``generation_config`` (API camelCase, e.g. ``responseMimeType``,
        ``responseSchema``, ``stopSequences``, ``topP``, ``topK``,
        ``candidateCount``) are merged on top and win on conflict.

        Returns:
            The assembled ``generateContent`` / ``streamGenerateContent``
            request body.
        """
        payload: dict[str, Any] = {"contents": self._wrap_contents(contents)}

        gen_config: dict[str, Any] = {}
        if temperature is not None:
            gen_config["temperature"] = temperature
        if max_output_tokens is not None:
            gen_config["maxOutputTokens"] = max_output_tokens
        if generation_config:
            gen_config.update(generation_config)
        if gen_config:
            payload["generationConfig"] = gen_config

        if system_instruction is not None:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
        if tools is not None:
            payload["tools"] = tools
        if tool_config is not None:
            payload["toolConfig"] = tool_config
        if safety_settings is not None:
            payload["safetySettings"] = safety_settings
        if cached_content is not None:
            payload["cachedContent"] = self._cache_path(cached_content)
        return payload

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute an authenticated HTTP request against the Gemini API.

        Args:
            method: HTTP method (GET, POST, PATCH, DELETE, etc.).
            path: API path relative to base_url (e.g. ``/models``).
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

    async def _stream_request(
        self,
        path: str,
        *,
        json_body: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """POST to an SSE streaming endpoint and collect the parsed chunks.

        Reads the ``text/event-stream`` response line by line, parsing each
        ``data: {...}`` line into a chunk dict. On a non-2xx status the body
        is materialised so the shared typed-error mapper produces the same
        exceptions as :meth:`_request`.

        Args:
            path: API path relative to base_url (incl. ``?alt=sse``).
            json_body: JSON request body.

        Returns:
            The list of parsed ``GenerateContentResponse`` chunk dicts.

        Raises:
            toolsconnector.errors.APIError (subclass): On any non-2xx response
                (same mapping as :meth:`_request`).
        """
        chunks: list[dict[str, Any]] = []
        async with (
            httpx.AsyncClient(timeout=self._timeout) as client,
            client.stream(
                "POST",
                f"{self._base_url}{path}",
                headers=self._get_headers(),
                json=json_body,
            ) as response,
        ):
            if response.status_code >= 400:
                # Materialise the body so raise_typed_for_status can read it.
                await response.aread()
                raise_typed_for_status(response, connector=self.name)
            async for raw_line in response.aiter_lines():
                line = raw_line.strip()
                if not line.startswith("data:"):
                    continue
                payload = line[len("data:") :].strip()
                if not payload:
                    continue
                try:
                    parsed = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                # Each alt=sse event is a single GenerateContentResponse
                # OBJECT. Guard against the non-SSE JSON-array form leaking
                # in (e.g. a proxy stripping ?alt=sse) so the assembler
                # degrades instead of crashing on list.get.
                if isinstance(parsed, dict):
                    chunks.append(parsed)
                elif isinstance(parsed, list):
                    chunks.extend(c for c in parsed if isinstance(c, dict))
        return chunks

    # ------------------------------------------------------------------
    # Actions -- Content generation
    # ------------------------------------------------------------------

    @action("Generate content with a Gemini model")
    async def generate_content(
        self,
        model: str,
        contents: Union[str, list[dict[str, Any]]],
        system_instruction: Optional[str] = None,
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
        cached_content: Optional[str] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        tool_config: Optional[dict[str, Any]] = None,
        safety_settings: Optional[list[dict[str, Any]]] = None,
        generation_config: Optional[dict[str, Any]] = None,
    ) -> GeminiResponse:
        """Generate content (text) from a prompt using the specified model.

        Args:
            model: Model id to use (e.g. ``'gemini-2.0-flash'``). May include
                the ``models/`` prefix or be a ``tunedModels/{id}`` reference.
            contents: Either a plain prompt string (wrapped automatically into
                a single user turn) or a pre-built list of content dicts, each
                with ``role`` and ``parts`` keys for multi-turn conversations.
            system_instruction: Optional system prompt that steers the model's
                behaviour for the whole request.
            temperature: Sampling temperature between 0.0 and 2.0.
            max_output_tokens: Maximum number of tokens to generate.
            cached_content: Optional ``cachedContents/{id}`` reference. When
                set, the cached context is prepended and billed at the cached
                rate (the cache's model must match ``model``).
            tools: Optional list of tool declarations for function calling
                (each typically ``{"functionDeclarations": [...]}``). The model
                may then return a ``functionCall`` part in the response.
            tool_config: Optional ``toolConfig`` controlling function-calling
                mode (e.g. ``{"functionCallingConfig": {"mode": "ANY"}}``).
            safety_settings: Optional list of ``{"category": ..., "threshold":
                ...}`` dicts overriding the default safety thresholds.
            generation_config: Optional extra ``generationConfig`` keys (API
                camelCase) merged over ``temperature``/``max_output_tokens`` —
                e.g. ``responseMimeType`` + ``responseSchema`` for structured
                JSON output, ``stopSequences``, ``topP``, ``topK``,
                ``candidateCount``.

        Returns:
            GeminiResponse with the concatenated text, finish reason, token
            usage, typed safety/citation/block-reason fields, and the raw
            candidate list.
        """
        payload = self._build_generation_payload(
            contents=contents,
            system_instruction=system_instruction,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            tools=tools,
            tool_config=tool_config,
            safety_settings=safety_settings,
            generation_config=generation_config,
            cached_content=cached_content,
        )

        data = await self._request(
            "POST",
            f"/{self._model_path(model)}:generateContent",
            json=payload,
        )

        return parse_generate_response(data)

    @action("Count tokens for a prompt", idempotent=True)
    async def count_tokens(
        self,
        model: str,
        contents: Union[str, list[dict[str, Any]]],
    ) -> TokenCount:
        """Count the number of tokens a prompt would consume.

        Useful for estimating cost and ensuring a prompt fits within a
        model's context window before calling ``generate_content``.

        Args:
            model: Model id to count tokens for (e.g. ``'gemini-2.0-flash'``).
                May include the ``models/`` prefix or not.
            contents: Either a plain prompt string or a pre-built list of
                content dicts with ``role`` and ``parts`` keys.

        Returns:
            TokenCount with the total token count for the prompt.
        """
        data = await self._request(
            "POST",
            f"/{self._model_path(model)}:countTokens",
            json={"contents": self._wrap_contents(contents)},
        )

        return TokenCount(
            total_tokens=data.get("totalTokens", 0),
            cached_content_token_count=data.get("cachedContentTokenCount", 0),
        )

    @action("Stream content generation with a Gemini model (server-sent events)")
    async def stream_generate_content(
        self,
        model: str,
        contents: Union[str, list[dict[str, Any]]],
        system_instruction: Optional[str] = None,
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
        cached_content: Optional[str] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        tool_config: Optional[dict[str, Any]] = None,
        safety_settings: Optional[list[dict[str, Any]]] = None,
        generation_config: Optional[dict[str, Any]] = None,
    ) -> GeminiStreamResult:
        """Generate content via the streaming endpoint (``:streamGenerateContent``).

        Calls the SSE streaming endpoint and assembles the partial chunks into
        a single :class:`GeminiStreamResult`: ``text`` is the full output,
        ``chunks`` holds each text delta in order, and ``finish_reason`` /
        ``usage`` come from the final chunk. Accepts the same generation,
        tools, and safety options as :meth:`generate_content`.

        Returning one assembled value (rather than an async iterator) keeps the
        action consistent with the typed / MCP contract; the SSE endpoint is
        still used end to end.

        Args:
            model: Model id to use (e.g. ``'gemini-2.0-flash'``).
            contents: A prompt string or a list of content dicts.
            system_instruction: Optional system prompt.
            temperature: Sampling temperature between 0.0 and 2.0.
            max_output_tokens: Maximum number of tokens to generate.
            cached_content: Optional ``cachedContents/{id}`` reference.
            tools: Optional function-calling tool declarations.
            tool_config: Optional ``toolConfig`` for function-calling mode.
            safety_settings: Optional safety-threshold overrides.
            generation_config: Optional extra ``generationConfig`` keys
                (API camelCase), merged over ``temperature`` /
                ``max_output_tokens``.

        Returns:
            GeminiStreamResult with the assembled text, per-chunk deltas,
            finish reason, and token usage.
        """
        payload = self._build_generation_payload(
            contents=contents,
            system_instruction=system_instruction,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            tools=tools,
            tool_config=tool_config,
            safety_settings=safety_settings,
            generation_config=generation_config,
            cached_content=cached_content,
        )

        chunks = await self._stream_request(
            f"/{self._model_path(model)}:streamGenerateContent?alt=sse",
            json_body=payload,
        )

        return assemble_stream_result(chunks)

    # ------------------------------------------------------------------
    # Actions -- Embeddings
    # ------------------------------------------------------------------

    @action("Create an embedding for a single text")
    async def embed_content(
        self,
        model: str,
        text: str,
        task_type: Optional[str] = None,
        title: Optional[str] = None,
        output_dimensionality: Optional[int] = None,
    ) -> Embedding:
        """Create an embedding vector for a single piece of text.

        Args:
            model: Embedding model id (e.g. ``'gemini-embedding-001'``). May
                include the ``models/`` prefix or not.
            text: The text to embed.
            task_type: Optional intended task, e.g. ``'RETRIEVAL_QUERY'``,
                ``'RETRIEVAL_DOCUMENT'``, ``'SEMANTIC_SIMILARITY'``,
                ``'CLASSIFICATION'``, ``'CLUSTERING'``, ``'QUESTION_ANSWERING'``,
                ``'FACT_VERIFICATION'``, or ``'CODE_RETRIEVAL_QUERY'``.
            title: Optional document title, only used with the
                ``'RETRIEVAL_DOCUMENT'`` task type.
            output_dimensionality: Optional reduced output dimension; truncates
                the embedding to this many values when the model supports it.

        Returns:
            Embedding with the vector ``values``.
        """
        payload: dict[str, Any] = {"content": {"parts": [{"text": text}]}}
        if task_type is not None:
            payload["taskType"] = task_type
        if title is not None:
            payload["title"] = title
        if output_dimensionality is not None:
            payload["outputDimensionality"] = output_dimensionality

        data = await self._request(
            "POST",
            f"/{self._model_path(model)}:embedContent",
            json=payload,
        )

        embedding = data.get("embedding", {})
        return Embedding(values=embedding.get("values", []))

    @action("Create embeddings for multiple texts")
    async def batch_embed_contents(
        self,
        model: str,
        texts: list[str],
        task_type: Optional[str] = None,
    ) -> BatchEmbeddings:
        """Create embedding vectors for several texts in a single request.

        Args:
            model: Embedding model id (e.g. ``'gemini-embedding-001'``). May
                include the ``models/`` prefix or not.
            texts: The list of texts to embed.
            task_type: Optional task type applied to every text in the batch
                (e.g. ``'RETRIEVAL_DOCUMENT'``).

        Returns:
            BatchEmbeddings with one Embedding per input text, in order.
        """
        model_ref = self._model_path(model)
        requests: list[dict[str, Any]] = []
        for text in texts:
            req: dict[str, Any] = {
                "model": model_ref,
                "content": {"parts": [{"text": text}]},
            }
            if task_type is not None:
                req["taskType"] = task_type
            requests.append(req)

        data = await self._request(
            "POST",
            f"/{model_ref}:batchEmbedContents",
            json={"requests": requests},
        )

        embeddings = [Embedding(values=e.get("values", [])) for e in data.get("embeddings", [])]
        return BatchEmbeddings(embeddings=embeddings)

    # ------------------------------------------------------------------
    # Actions -- Models
    # ------------------------------------------------------------------

    @action("List available Gemini models", idempotent=True)
    async def list_models(self) -> list[GeminiModel]:
        """List all models available to the authenticated API key.

        Returns:
            List of GeminiModel objects with model metadata.
        """
        data = await self._request("GET", "/models")
        return [parse_model(m) for m in data.get("models", [])]

    @action("Get a model by ID", idempotent=True)
    async def get_model(self, model: str) -> GeminiModel:
        """Retrieve metadata about a specific Gemini model.

        Args:
            model: The model id (e.g. ``'gemini-2.0-flash'``). May include the
                ``models/`` prefix or not.

        Returns:
            GeminiModel with the model's metadata and capabilities.
        """
        data = await self._request("GET", f"/{self._model_path(model)}")
        return parse_model(data)

    # ------------------------------------------------------------------
    # Actions -- Files API
    # ------------------------------------------------------------------

    @action("Upload a file to the Gemini Files API")
    async def upload_file(
        self,
        file_content: bytes,
        mime_type: str,
        display_name: Optional[str] = None,
    ) -> GeminiFile:
        """Upload media (image, audio, video, PDF, text) for use in prompts.

        Uses the resumable upload protocol: a ``start`` request registers the
        file metadata and returns an upload URL, then the bytes are sent with
        ``upload, finalize`` in a single follow-up request. The returned
        ``uri`` can be referenced from ``generate_content`` via a ``fileData``
        part.

        Args:
            file_content: Raw file bytes to upload.
            mime_type: The IANA media type of the content (e.g.
                ``'image/png'``, ``'application/pdf'``, ``'audio/mp3'``).
            display_name: Optional human-readable name for the file.

        Returns:
            The created GeminiFile with its ``name``, ``uri``, and ``state``.
        """
        upload_base = self._upload_base()
        size = str(len(file_content))
        metadata: dict[str, Any] = {}
        if display_name is not None:
            metadata["file"] = {"displayName": display_name}

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            start = await client.post(
                f"{upload_base}/files",
                headers={
                    "x-goog-api-key": str(self._credentials),
                    "X-Goog-Upload-Protocol": "resumable",
                    "X-Goog-Upload-Command": "start",
                    "X-Goog-Upload-Header-Content-Length": size,
                    "X-Goog-Upload-Header-Content-Type": mime_type,
                    "Content-Type": "application/json",
                },
                json=metadata,
            )
            raise_typed_for_status(start, connector=self.name)
            upload_url = start.headers.get("x-goog-upload-url") or f"{upload_base}/files"

            response = await client.post(
                upload_url,
                headers={
                    "x-goog-api-key": str(self._credentials),
                    "Content-Length": size,
                    "X-Goog-Upload-Offset": "0",
                    "X-Goog-Upload-Command": "upload, finalize",
                },
                content=file_content,
            )
            raise_typed_for_status(response, connector=self.name)
            data = response.json()

        return parse_file(data)

    @action("Get file metadata by name", idempotent=True)
    async def get_file(self, name: str) -> GeminiFile:
        """Retrieve metadata for an uploaded file.

        Args:
            name: The file resource name (e.g. ``'files/abc-123'``). May
                include the ``files/`` prefix or not.

        Returns:
            GeminiFile with the file's metadata and processing ``state``.
        """
        data = await self._request("GET", f"/{self._file_path(name)}")
        return parse_file(data)

    @action("List uploaded files", idempotent=True)
    async def list_files(
        self,
        page_size: Optional[int] = None,
        page_token: Optional[str] = None,
    ) -> FileList:
        """List files uploaded to the Files API for this API key.

        Args:
            page_size: Maximum number of files to return per page (1-100,
                default 10).
            page_token: Continuation token from a previous response's
                ``next_page_token`` to fetch the next page.

        Returns:
            FileList with the page of files and a ``next_page_token`` when
            more results remain.
        """
        params: dict[str, Any] = {}
        if page_size is not None:
            params["pageSize"] = page_size
        if page_token is not None:
            params["pageToken"] = page_token

        data = await self._request("GET", "/files", params=params or None)
        return FileList(
            files=[parse_file(f) for f in data.get("files", [])],
            next_page_token=data.get("nextPageToken"),
        )

    @action("Delete an uploaded file", dangerous=True)
    async def delete_file(self, name: str) -> bool:
        """Permanently delete an uploaded file.

        Args:
            name: The file resource name (e.g. ``'files/abc-123'``). May
                include the ``files/`` prefix or not.

        Returns:
            True once the delete request succeeds.
        """
        await self._request("DELETE", f"/{self._file_path(name)}")
        return True

    # ------------------------------------------------------------------
    # Actions -- Context caching (cachedContents)
    # ------------------------------------------------------------------

    @action("Create a context cache")
    async def create_cache(
        self,
        model: str,
        contents: Optional[list[dict[str, Any]]] = None,
        system_instruction: Optional[str] = None,
        ttl: Optional[str] = None,
        display_name: Optional[str] = None,
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> CachedContent:
        """Create a reusable context cache for a model.

        Caching uploads a large, reused context once so subsequent
        ``generate_content`` calls (passing ``cached_content``) skip
        re-sending and re-billing those tokens at the full rate.

        Args:
            model: The model the cache is bound to (e.g.
                ``'gemini-2.0-flash-001'``). The cache is immutable to this
                model. May include the ``models/`` prefix or not.
            contents: Cached conversation turns, each a content dict with
                ``role`` and ``parts`` keys.
            system_instruction: Optional cached system prompt.
            ttl: Optional time-to-live as a duration string (e.g. ``'300s'``).
                Defaults to one hour server-side when omitted.
            display_name: Optional human-readable name (max 128 chars).
            tools: Optional cached tool/function declarations.

        Returns:
            The created CachedContent with its ``name`` and ``expire_time``.
        """
        payload: dict[str, Any] = {"model": self._model_path(model)}
        if contents is not None:
            payload["contents"] = contents
        if system_instruction is not None:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
        if ttl is not None:
            payload["ttl"] = ttl
        if display_name is not None:
            payload["displayName"] = display_name
        if tools is not None:
            payload["tools"] = tools

        data = await self._request("POST", "/cachedContents", json=payload)
        return parse_cached_content(data)

    @action("Get a context cache by name", idempotent=True)
    async def get_cache(self, name: str) -> CachedContent:
        """Retrieve metadata for a context cache.

        Args:
            name: The cache resource name (e.g. ``'cachedContents/abc'``).
                May include the ``cachedContents/`` prefix or not.

        Returns:
            The CachedContent with its current ``expire_time`` and usage.
        """
        data = await self._request("GET", f"/{self._cache_path(name)}")
        return parse_cached_content(data)

    @action("List context caches", idempotent=True)
    async def list_caches(
        self,
        page_size: Optional[int] = None,
        page_token: Optional[str] = None,
    ) -> CachedContentList:
        """List context caches owned by this API key.

        Args:
            page_size: Maximum number of caches to return per page.
            page_token: Continuation token from a previous response's
                ``next_page_token``.

        Returns:
            CachedContentList with the page of caches and a
            ``next_page_token`` when more results remain.
        """
        params: dict[str, Any] = {}
        if page_size is not None:
            params["pageSize"] = page_size
        if page_token is not None:
            params["pageToken"] = page_token

        data = await self._request("GET", "/cachedContents", params=params or None)
        return CachedContentList(
            cached_contents=[parse_cached_content(c) for c in data.get("cachedContents", [])],
            next_page_token=data.get("nextPageToken"),
        )

    @action("Update a context cache's expiration")
    async def update_cache(
        self,
        name: str,
        ttl: Optional[str] = None,
        expire_time: Optional[str] = None,
    ) -> CachedContent:
        """Update a context cache's expiration (``ttl`` or ``expire_time``).

        Only the expiration is mutable; supply exactly one of ``ttl`` or
        ``expire_time``. The matching field name is sent as the
        ``updateMask`` so only that field is changed.

        Args:
            name: The cache resource name (e.g. ``'cachedContents/abc'``).
                May include the ``cachedContents/`` prefix or not.
            ttl: New time-to-live as a duration string (e.g. ``'600s'``),
                relative to now.
            expire_time: New absolute expiry as an RFC 3339 timestamp (e.g.
                ``'2026-01-01T00:00:00Z'``).

        Returns:
            The updated CachedContent.
        """
        payload: dict[str, Any] = {}
        update_mask: list[str] = []
        if ttl is not None:
            payload["ttl"] = ttl
            update_mask.append("ttl")
        if expire_time is not None:
            payload["expireTime"] = expire_time
            update_mask.append("expireTime")

        params = {"updateMask": ",".join(update_mask)} if update_mask else None
        data = await self._request(
            "PATCH",
            f"/{self._cache_path(name)}",
            params=params,
            json=payload,
        )
        return parse_cached_content(data)

    @action("Delete a context cache", dangerous=True)
    async def delete_cache(self, name: str) -> bool:
        """Permanently delete a context cache.

        Args:
            name: The cache resource name (e.g. ``'cachedContents/abc'``).
                May include the ``cachedContents/`` prefix or not.

        Returns:
            True once the delete request succeeds.
        """
        await self._request("DELETE", f"/{self._cache_path(name)}")
        return True

    # ------------------------------------------------------------------
    # Actions -- Tuned models
    # ------------------------------------------------------------------

    @action(
        "List tuned models",
        idempotent=True,
        deprecated=True,
        deprecation_message="Google discontinued model tuning on the public Gemini API (the tunedModels endpoints return HTTP 501, verified live 2026-06-12); tune via Vertex AI instead.",
    )
    async def list_tuned_models(
        self,
        page_size: Optional[int] = None,
        page_token: Optional[str] = None,
        filter: Optional[str] = None,
    ) -> TunedModelList:
        """List tuned (fine-tuned) models visible to this API key.

        Args:
            page_size: Maximum number of tuned models to return per page
                (default 10).
            page_token: Continuation token from a previous response's
                ``next_page_token``.
            filter: Optional filter expression (e.g. ``'owner:me'`` or
                ``'readers:everyone'``).

        Returns:
            TunedModelList with the page of tuned models and a
            ``next_page_token`` when more results remain.
        """
        params: dict[str, Any] = {}
        if page_size is not None:
            params["pageSize"] = page_size
        if page_token is not None:
            params["pageToken"] = page_token
        if filter is not None:
            params["filter"] = filter

        data = await self._request("GET", "/tunedModels", params=params or None)
        return TunedModelList(
            tuned_models=[parse_tuned_model(m) for m in data.get("tunedModels", [])],
            next_page_token=data.get("nextPageToken"),
        )

    @action(
        "Get a tuned model by name",
        idempotent=True,
        deprecated=True,
        deprecation_message="Google discontinued model tuning on the public Gemini API (the tunedModels endpoints return HTTP 501, verified live 2026-06-12); tune via Vertex AI instead.",
    )
    async def get_tuned_model(self, name: str) -> TunedModel:
        """Retrieve metadata about a tuned model, including its tuning state.

        Args:
            name: The tuned model resource name (e.g.
                ``'tunedModels/my-model-123'``). May include the
                ``tunedModels/`` prefix or not.

        Returns:
            TunedModel with its ``state`` (``CREATING``/``ACTIVE``/``FAILED``)
            and base model.
        """
        data = await self._request("GET", f"/{self._tuned_model_path(name)}")
        return parse_tuned_model(data)

    @action(
        "Create a tuned model",
        dangerous=True,
        deprecated=True,
        deprecation_message="Google discontinued model tuning on the public Gemini API (the tunedModels endpoints return HTTP 501, verified live 2026-06-12); tune via Vertex AI instead.",
    )
    async def create_tuned_model(
        self,
        base_model: str,
        training_data: list[dict[str, str]],
        display_name: Optional[str] = None,
        tuned_model_id: Optional[str] = None,
        epoch_count: Optional[int] = None,
        batch_size: Optional[int] = None,
        learning_rate: Optional[float] = None,
    ) -> TunedModel:
        """Start a tuning job that creates a new tuned model.

        The job runs asynchronously: the returned model begins in the
        ``CREATING`` state. Poll ``get_tuned_model`` until it reaches
        ``ACTIVE`` before using it for generation.

        Args:
            base_model: Foundation model to tune (e.g. ``'gemini-2.0-flash'``).
                May include the ``models/`` prefix or not.
            training_data: Training examples, each a dict with ``text_input``
                and ``output`` keys.
            display_name: Optional human-readable name for the tuned model.
            tuned_model_id: Optional explicit id (lowercase letters, digits,
                and dashes; max 40 chars). Auto-generated when omitted.
            epoch_count: Optional number of training epochs.
            batch_size: Optional training batch size.
            learning_rate: Optional learning rate for the tuning task.

        Returns:
            The created TunedModel in its initial ``CREATING`` state.
        """
        hyperparameters: dict[str, Any] = {}
        if epoch_count is not None:
            hyperparameters["epochCount"] = epoch_count
        if batch_size is not None:
            hyperparameters["batchSize"] = batch_size
        if learning_rate is not None:
            hyperparameters["learningRate"] = learning_rate

        tuning_task: dict[str, Any] = {
            "trainingData": {
                "examples": {
                    "examples": [
                        {"textInput": ex.get("text_input", ""), "output": ex.get("output", "")}
                        for ex in training_data
                    ]
                }
            }
        }
        if hyperparameters:
            tuning_task["hyperparameters"] = hyperparameters

        payload: dict[str, Any] = {
            "baseModel": self._model_path(base_model),
            "tuningTask": tuning_task,
        }
        if display_name is not None:
            payload["displayName"] = display_name

        params = {"tunedModelId": tuned_model_id} if tuned_model_id is not None else None
        data = await self._request("POST", "/tunedModels", params=params, json=payload)
        # Create returns a long-running Operation; the tuned model metadata is
        # nested on its ``metadata`` field, falling back to the raw body.
        resource = data.get("metadata", {}).get("tunedModel") if "metadata" in data else None
        return parse_tuned_model(resource or data)

    @action(
        "Delete a tuned model",
        dangerous=True,
        deprecated=True,
        deprecation_message="Google discontinued model tuning on the public Gemini API (the tunedModels endpoints return HTTP 501, verified live 2026-06-12); tune via Vertex AI instead.",
    )
    async def delete_tuned_model(self, name: str) -> bool:
        """Permanently delete a tuned model.

        Args:
            name: The tuned model resource name (e.g.
                ``'tunedModels/my-model-123'``). May include the
                ``tunedModels/`` prefix or not.

        Returns:
            True once the delete request succeeds.
        """
        await self._request("DELETE", f"/{self._tuned_model_path(name)}")
        return True
