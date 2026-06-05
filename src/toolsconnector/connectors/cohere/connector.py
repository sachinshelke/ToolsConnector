"""Cohere connector -- chat, embeddings, rerank, classify, tokenization, and async jobs.

Uses httpx for direct HTTP calls against the Cohere REST API. Cohere mixes
v1 and v2 endpoints, so the API version is carried in each request path
rather than the ``base_url``. Expects a Bearer API key passed as
``credentials`` (BYOK).

Surface:

* **Inference** -- chat (``/v2/chat``), embed (``/v2/embed``),
  rerank (``/v2/rerank``), classify (``/v1/classify``),
  tokenize / detokenize (``/v1``).
* **Models** -- list / get (``/v1/models``).
* **Embed jobs** -- batch embeddings over a dataset (``/v1/embed-jobs``).
* **Datasets** -- upload / list / get / delete / usage (``/v1/datasets``).
* **Fine-tuning** -- create / list / get / delete finetuned models
  (``/v1/finetuning``).
* **Auth** -- check API key (``/v1/check-api-key``).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from toolsconnector.connectors._helpers import raise_typed_for_status
from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import (
    ConnectorCategory,
    ProtocolType,
    RateLimitSpec,
)

from ._parsers import (
    parse_api_key_check,
    parse_dataset,
    parse_dataset_usage,
    parse_embed_job,
    parse_finetuned_model,
    parse_model,
    parse_usage,
)
from .types import (
    ApiKeyCheck,
    ChatResponse,
    ClassifyPrediction,
    ClassifyResponse,
    CohereModel,
    Dataset,
    DatasetUsage,
    DetokenizeResponse,
    EmbedJob,
    EmbedResponse,
    FinetunedModel,
    RerankResponse,
    RerankResult,
    TokenizeResponse,
)

logger = logging.getLogger("toolsconnector.cohere")


class Cohere(BaseConnector):
    """Connect to Cohere for chat, embeddings, rerank, classification, jobs, and tuning.

    Supports Bearer token authentication. Pass an API key as
    ``credentials`` when instantiating. Uses the Cohere REST API via
    direct httpx calls. Cohere mixes v1 and v2 endpoints, so the version
    is included in each request path.
    """

    name = "cohere"
    display_name = "Cohere"
    category = ConnectorCategory.AI_ML
    protocol = ProtocolType.REST
    base_url = "https://api.cohere.com"
    description = (
        "Connect to Cohere for chat completions, text embeddings, document "
        "reranking, text classification, tokenization, batch embed jobs, "
        "dataset management, and model fine-tuning."
    )
    verification_status = "pattern"
    _rate_limit_config = RateLimitSpec(rate=60, period=60, burst=20)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_headers(self) -> dict[str, str]:
        """Build authorization headers for Cohere API requests.

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
        """Execute an authenticated HTTP request against the Cohere API.

        Args:
            method: HTTP method (GET, POST, DELETE, etc.).
            path: API path relative to base_url, including the version
                segment (e.g. ``"/v2/chat"`` or ``"/v1/models"``).
            **kwargs: Additional keyword arguments passed to httpx.

        Returns:
            Parsed JSON response as a dict. Empty dict for 204/no-content
            responses (e.g. embed-job cancel).

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

    # ------------------------------------------------------------------
    # Actions -- Chat
    # ------------------------------------------------------------------

    @action("Generate a chat response")
    async def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        documents: Optional[list[dict[str, Any]]] = None,
        response_format: Optional[dict[str, Any]] = None,
    ) -> ChatResponse:
        """Generate a chat response using the specified model (``/v2/chat``).

        Args:
            model: Model ID to use (e.g., ``'command-r-plus'``).
            messages: List of message dicts with ``'role'`` and ``'content'``
                keys, e.g. ``[{"role": "user", "content": "Hello"}]``.
            temperature: Sampling temperature (Cohere accepts 0.0-1.0).
            max_tokens: Maximum number of tokens to generate.
            tools: Tool/function definitions the model may call, each an
                OpenAI-style ``{"type": "function", "function": {...}}`` dict.
            documents: Grounding documents for retrieval-augmented generation,
                each a dict (e.g. ``{"id": "doc1", "data": {...}}``).
            response_format: Structured-output spec, e.g.
                ``{"type": "json_object"}`` or a JSON schema.

        Returns:
            ChatResponse with the assistant text and token usage.
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
        if documents is not None:
            payload["documents"] = documents
        if response_format is not None:
            payload["response_format"] = response_format

        data = await self._request("POST", "/v2/chat", json=payload)

        message = data.get("message", {}) or {}
        content_blocks = message.get("content", []) or []
        text = ""
        for block in content_blocks:
            if block.get("type", "text") == "text" and block.get("text"):
                text = block["text"]
                break
        if not text and content_blocks:
            text = content_blocks[0].get("text", "") or ""

        return ChatResponse(
            id=data.get("id", ""),
            text=text,
            role=message.get("role", "assistant"),
            finish_reason=data.get("finish_reason"),
            content_blocks=content_blocks,
            usage=parse_usage(data.get("usage")),
        )

    # ------------------------------------------------------------------
    # Actions -- Embeddings
    # ------------------------------------------------------------------

    @action("Create text embeddings")
    async def embed(
        self,
        model: str,
        texts: list[str],
        input_type: str,
        embedding_types: Optional[list[str]] = None,
        truncate: Optional[str] = None,
    ) -> EmbedResponse:
        """Create embedding vectors for the given input texts (``/v2/embed``).

        Args:
            model: Model ID to use (e.g., ``'embed-english-v3.0'``).
            texts: List of strings to embed.
            input_type: Embedding input type. One of ``'search_document'``,
                ``'search_query'``, ``'classification'``, ``'clustering'``,
                or ``'image'``.
            embedding_types: Embedding formats to return (e.g.
                ``['float']``, ``['int8']``, ``['binary']``). Defaults to
                ``['float']`` when omitted.
            truncate: How to handle inputs longer than the context length.
                One of ``'NONE'``, ``'START'``, or ``'END'`` (default ``'END'``).

        Returns:
            EmbedResponse with embeddings keyed by embedding type.
        """
        payload: dict[str, Any] = {
            "model": model,
            "texts": texts,
            "input_type": input_type,
            "embedding_types": embedding_types if embedding_types is not None else ["float"],
        }
        if truncate is not None:
            payload["truncate"] = truncate

        data = await self._request("POST", "/v2/embed", json=payload)

        return EmbedResponse(
            id=data.get("id", ""),
            embeddings=data.get("embeddings", {}) or {},
            texts=data.get("texts", []) or [],
            usage=parse_usage(data.get("usage")),
        )

    # ------------------------------------------------------------------
    # Actions -- Rerank
    # ------------------------------------------------------------------

    @action("Rerank documents by relevance to a query")
    async def rerank(
        self,
        model: str,
        query: str,
        documents: list[str],
        top_n: Optional[int] = None,
        max_tokens_per_doc: Optional[int] = None,
    ) -> RerankResponse:
        """Rerank a list of documents by relevance to a query (``/v2/rerank``).

        Args:
            model: Rerank model ID (e.g., ``'rerank-english-v3.0'``).
            query: The search query to rank documents against.
            documents: List of document strings to rerank.
            top_n: Number of top results to return. Returns all documents
                ranked when omitted.
            max_tokens_per_doc: Truncate documents to this many tokens
                before reranking.

        Returns:
            RerankResponse with results ordered by relevance score.
        """
        payload: dict[str, Any] = {
            "model": model,
            "query": query,
            "documents": documents,
        }
        if top_n is not None:
            payload["top_n"] = top_n
        if max_tokens_per_doc is not None:
            payload["max_tokens_per_doc"] = max_tokens_per_doc

        data = await self._request("POST", "/v2/rerank", json=payload)

        results = [
            RerankResult(
                index=r.get("index", 0),
                relevance_score=r.get("relevance_score", 0.0),
            )
            for r in data.get("results", [])
        ]

        return RerankResponse(id=data.get("id", ""), results=results)

    # ------------------------------------------------------------------
    # Actions -- Classify
    # ------------------------------------------------------------------

    @action("Classify text into labelled categories")
    async def classify(
        self,
        model: str,
        inputs: list[str],
        examples: list[dict[str, Any]],
    ) -> ClassifyResponse:
        """Classify input texts using few-shot labelled examples (``/v1/classify``).

        Args:
            model: Classification model ID (e.g.,
                ``'embed-english-v3.0'``).
            inputs: List of strings to classify.
            examples: Labelled example dicts, each with ``'text'`` and
                ``'label'`` keys, used as few-shot training data.

        Returns:
            ClassifyResponse with one prediction per input.
        """
        payload: dict[str, Any] = {
            "model": model,
            "inputs": inputs,
            "examples": examples,
        }

        data = await self._request("POST", "/v1/classify", json=payload)

        classifications = [
            ClassifyPrediction(
                input=c.get("input", ""),
                prediction=c.get("prediction"),
                confidence=c.get("confidence"),
                labels=c.get("labels", {}) or {},
            )
            for c in data.get("classifications", [])
        ]

        return ClassifyResponse(id=data.get("id", ""), classifications=classifications)

    # ------------------------------------------------------------------
    # Actions -- Tokenization
    # ------------------------------------------------------------------

    @action("Tokenize text into token IDs", idempotent=True)
    async def tokenize(
        self,
        model: str,
        text: str,
    ) -> TokenizeResponse:
        """Split text into tokens using the model's tokenizer (``/v1/tokenize``).

        Args:
            model: Model ID whose tokenizer to use (e.g.,
                ``'command-r-plus'``).
            text: The text to tokenize.

        Returns:
            TokenizeResponse with token IDs and their string forms.
        """
        payload: dict[str, Any] = {"model": model, "text": text}

        data = await self._request("POST", "/v1/tokenize", json=payload)

        return TokenizeResponse(
            tokens=data.get("tokens", []) or [],
            token_strings=data.get("token_strings", []) or [],
        )

    @action("Convert token IDs back into text", idempotent=True)
    async def detokenize(
        self,
        model: str,
        tokens: list[int],
    ) -> DetokenizeResponse:
        """Reconstruct text from a list of token IDs (``/v1/detokenize``).

        Args:
            model: Model ID whose tokenizer to use (e.g.,
                ``'command-r-plus'``).
            tokens: List of integer token IDs to convert back to text.

        Returns:
            DetokenizeResponse with the reconstructed text.
        """
        payload: dict[str, Any] = {"model": model, "tokens": tokens}

        data = await self._request("POST", "/v1/detokenize", json=payload)

        return DetokenizeResponse(text=data.get("text", ""))

    # ------------------------------------------------------------------
    # Actions -- Models
    # ------------------------------------------------------------------

    @action("List available Cohere models", idempotent=True)
    async def list_models(
        self,
        endpoint: Optional[str] = None,
        default_only: Optional[bool] = None,
    ) -> list[CohereModel]:
        """List models available to the authenticated account (``/v1/models``).

        Args:
            endpoint: Filter to models that support this endpoint
                (e.g. ``'chat'``, ``'embed'``, ``'rerank'``, ``'classify'``).
            default_only: When True, return only Cohere's default models.

        Returns:
            List of CohereModel objects with model metadata.
        """
        params: dict[str, Any] = {}
        if endpoint is not None:
            params["endpoint"] = endpoint
        if default_only is not None:
            params["default_only"] = default_only

        data = await self._request("GET", "/v1/models", params=params or None)

        return [parse_model(m) for m in data.get("models", [])]

    @action("Get a Cohere model by name", idempotent=True)
    async def get_model(self, model: str) -> CohereModel:
        """Retrieve metadata for a single model (``/v1/models/{model}``).

        Args:
            model: The model name to retrieve (e.g., ``'command-r-plus'``).

        Returns:
            CohereModel with the model's metadata.
        """
        data = await self._request("GET", f"/v1/models/{model}")
        return parse_model(data)

    # ------------------------------------------------------------------
    # Actions -- Embed jobs (batch embeddings)
    # ------------------------------------------------------------------

    @action("Create a batch embed job")
    async def create_embed_job(
        self,
        model: str,
        dataset_id: str,
        input_type: str,
        name: Optional[str] = None,
        embedding_types: Optional[list[str]] = None,
        truncate: Optional[str] = None,
    ) -> EmbedJob:
        """Launch a batch embedding job over a dataset (``/v1/embed-jobs``).

        Embeds every record in a validated ``embed-input`` dataset
        asynchronously, writing results to a new output dataset.

        Args:
            model: Embedding model ID (e.g., ``'embed-english-v3.0'``).
            dataset_id: ID of a validated ``embed-input`` dataset to embed.
            input_type: Embedding input type. One of ``'search_document'``,
                ``'search_query'``, ``'classification'``, ``'clustering'``,
                or ``'image'``.
            name: Optional human-readable name for the job.
            embedding_types: Embedding formats to produce (e.g. ``['float']``).
            truncate: How to handle over-length inputs -- ``'START'`` or
                ``'END'`` (default ``'END'``).

        Returns:
            EmbedJob with the new ``job_id`` (poll with ``get_embed_job``).
        """
        payload: dict[str, Any] = {
            "model": model,
            "dataset_id": dataset_id,
            "input_type": input_type,
        }
        if name is not None:
            payload["name"] = name
        if embedding_types is not None:
            payload["embedding_types"] = embedding_types
        if truncate is not None:
            payload["truncate"] = truncate

        data = await self._request("POST", "/v1/embed-jobs", json=payload)
        return parse_embed_job(data)

    @action("List batch embed jobs", idempotent=True)
    async def list_embed_jobs(self) -> list[EmbedJob]:
        """List all batch embed jobs for the account (``/v1/embed-jobs``).

        Returns:
            List of EmbedJob objects with their current status.
        """
        data = await self._request("GET", "/v1/embed-jobs")
        return [parse_embed_job(j) for j in data.get("embed_jobs", [])]

    @action("Get a batch embed job by ID", idempotent=True)
    async def get_embed_job(self, embed_job_id: str) -> EmbedJob:
        """Retrieve a batch embed job to check its status (``/v1/embed-jobs/{id}``).

        Args:
            embed_job_id: The embed-job ID to retrieve.

        Returns:
            EmbedJob with current status and output dataset (when complete).
        """
        data = await self._request("GET", f"/v1/embed-jobs/{embed_job_id}")
        return parse_embed_job(data)

    @action("Cancel a running batch embed job", dangerous=True)
    async def cancel_embed_job(self, embed_job_id: str) -> bool:
        """Cancel a running batch embed job (``/v1/embed-jobs/{id}/cancel``).

        Args:
            embed_job_id: The embed-job ID to cancel.

        Returns:
            True once the cancel request is accepted (Cohere returns an
            empty body on success).
        """
        await self._request("POST", f"/v1/embed-jobs/{embed_job_id}/cancel")
        return True

    # ------------------------------------------------------------------
    # Actions -- Datasets
    # ------------------------------------------------------------------

    @action("Create a dataset from an uploaded file")
    async def create_dataset(
        self,
        name: str,
        type: str,
        data: bytes,
        filename: Optional[str] = None,
        keep_original_file: Optional[bool] = None,
        skip_malformed_input: Optional[bool] = None,
        eval_data: Optional[bytes] = None,
    ) -> Dataset:
        """Upload a file as a new validated dataset (``/v1/datasets``).

        ``name`` and ``type`` travel as query parameters while the file
        is sent as ``multipart/form-data`` (Cohere's contract). The
        create call returns only the new dataset ``id``; this method then
        fetches the full dataset so callers get a populated model back.

        Args:
            name: Human-readable name for the dataset.
            type: Dataset type, e.g. ``'embed-input'``, ``'embed-result'``,
                ``'reranker-finetune-input'``, or ``'chat-finetune-input'``.
            data: Raw bytes of the dataset file (JSONL / CSV / TXT).
            filename: Name for the uploaded file part (default
                ``"data.jsonl"``).
            keep_original_file: Store the original uploaded file alongside
                the validated dataset.
            skip_malformed_input: Drop malformed rows instead of failing
                validation.
            eval_data: Optional raw bytes of an evaluation split file.

        Returns:
            The created Dataset (fetched after upload for full metadata).
        """
        upload_name = filename or "data.jsonl"
        params: dict[str, Any] = {"name": name, "type": type}
        if keep_original_file is not None:
            params["keep_original_file"] = keep_original_file
        if skip_malformed_input is not None:
            params["skip_malformed_input"] = skip_malformed_input

        files: dict[str, Any] = {"data": (upload_name, data)}
        if eval_data is not None:
            files["eval_data"] = ("eval.jsonl", eval_data)

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/v1/datasets",
                headers={"Authorization": f"Bearer {self._credentials}"},
                params=params,
                files=files,
            )
            raise_typed_for_status(response, connector=self.name)
            created = response.json() if response.content else {}

        dataset_id = created.get("id", "")
        # The create response carries only the id; fetch full metadata so
        # callers get a populated Dataset rather than a near-empty stub.
        if dataset_id:
            return await self.aget_dataset(dataset_id)
        return parse_dataset(created)

    @action("List datasets", idempotent=True)
    async def list_datasets(
        self,
        dataset_type: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> list[Dataset]:
        """List datasets for the account (``/v1/datasets``).

        Args:
            dataset_type: Filter by dataset type (e.g. ``'embed-input'``).
            limit: Maximum number of datasets to return.
            offset: Number of datasets to skip (for paging).

        Returns:
            List of Dataset objects.
        """
        params: dict[str, Any] = {}
        if dataset_type is not None:
            params["datasetType"] = dataset_type
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset

        data = await self._request("GET", "/v1/datasets", params=params or None)
        return [parse_dataset(d) for d in data.get("datasets", [])]

    @action("Get a dataset by ID", idempotent=True)
    async def get_dataset(self, dataset_id: str) -> Dataset:
        """Retrieve a dataset by ID (``/v1/datasets/{id}``).

        Args:
            dataset_id: The dataset ID to retrieve.

        Returns:
            The Dataset, including validation status and parts.
        """
        data = await self._request("GET", f"/v1/datasets/{dataset_id}")
        return parse_dataset(data.get("dataset", {}) or {})

    @action("Delete a dataset", dangerous=True)
    async def delete_dataset(self, dataset_id: str) -> bool:
        """Permanently delete a dataset (``/v1/datasets/{id}``).

        Args:
            dataset_id: The dataset ID to delete.

        Returns:
            True once the dataset is deleted (Cohere returns an empty
            body on success).
        """
        await self._request("DELETE", f"/v1/datasets/{dataset_id}")
        return True

    @action("Get organization dataset storage usage", idempotent=True)
    async def get_dataset_usage(self) -> DatasetUsage:
        """Get total dataset storage used by the org (``/v1/datasets/usage``).

        Returns:
            DatasetUsage with ``organization_usage`` in bytes.
        """
        data = await self._request("GET", "/v1/datasets/usage")
        return parse_dataset_usage(data)

    # ------------------------------------------------------------------
    # Actions -- Fine-tuning
    # ------------------------------------------------------------------

    @action("Create a fine-tuned model")
    async def create_finetuned_model(
        self,
        name: str,
        settings: dict[str, Any],
    ) -> FinetunedModel:
        """Start training a fine-tuned model (``/v1/finetuning/finetuned-models``).

        Args:
            name: Name for the fine-tuned model.
            settings: Training configuration dict. Must include a
                ``base_model`` object (e.g.
                ``{"base_type": "BASE_TYPE_CHAT"}``) and a ``dataset_id``;
                may include a ``hyperparameters`` object.

        Returns:
            The created FinetunedModel with its initial training status.
        """
        payload: dict[str, Any] = {"name": name, "settings": settings}
        data = await self._request(
            "POST",
            "/v1/finetuning/finetuned-models",
            json=payload,
        )
        return parse_finetuned_model(data.get("finetuned_model", {}) or {})

    @action("List fine-tuned models", idempotent=True)
    async def list_finetuned_models(self) -> list[FinetunedModel]:
        """List fine-tuned models (``/v1/finetuning/finetuned-models``).

        Returns:
            List of FinetunedModel objects.
        """
        data = await self._request("GET", "/v1/finetuning/finetuned-models")
        return [parse_finetuned_model(m) for m in data.get("finetuned_models", [])]

    @action("Get a fine-tuned model by ID", idempotent=True)
    async def get_finetuned_model(self, finetuned_model_id: str) -> FinetunedModel:
        """Retrieve a fine-tuned model by ID (``.../finetuned-models/{id}``).

        Args:
            finetuned_model_id: The fine-tuned model ID to retrieve.

        Returns:
            The FinetunedModel with current status and settings.
        """
        data = await self._request(
            "GET",
            f"/v1/finetuning/finetuned-models/{finetuned_model_id}",
        )
        return parse_finetuned_model(data.get("finetuned_model", {}) or {})

    @action("Delete a fine-tuned model", dangerous=True)
    async def delete_finetuned_model(self, finetuned_model_id: str) -> bool:
        """Permanently delete a fine-tuned model (``.../finetuned-models/{id}``).

        Args:
            finetuned_model_id: The fine-tuned model ID to delete.

        Returns:
            True once the model is deleted (Cohere returns an empty body
            on success).
        """
        await self._request(
            "DELETE",
            f"/v1/finetuning/finetuned-models/{finetuned_model_id}",
        )
        return True

    # ------------------------------------------------------------------
    # Actions -- Auth
    # ------------------------------------------------------------------

    @action("Check whether the API key is valid", idempotent=True)
    async def check_api_key(self) -> ApiKeyCheck:
        """Validate the configured API key (``/v1/check-api-key``).

        Returns:
            ApiKeyCheck with ``valid`` plus the org / owner IDs when valid.
        """
        data = await self._request("POST", "/v1/check-api-key")
        return parse_api_key_check(data)
