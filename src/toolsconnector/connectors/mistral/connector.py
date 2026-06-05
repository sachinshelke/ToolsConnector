"""Mistral connector -- chat, embeddings, FIM, agents, files, fine-tuning,
batch jobs, model management, OCR, and classifiers.

Uses httpx for direct HTTP calls against the Mistral AI REST API v1
(``https://api.mistral.ai/v1``). The core inference surface is
OpenAI-compatible; the platform-management surface follows Mistral's own
schemas (see https://docs.mistral.ai/api/). Expects a Bearer API key
passed as ``credentials`` (Bring Your Own Key).
"""

from __future__ import annotations

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

from . import _parsers as parsers
from .types import (
    AgentsCompletion,
    ArchiveModelResult,
    BatchJob,
    BatchJobDeleted,
    ChatCompletion,
    ClassificationResult,
    Embedding,
    FileDeleted,
    FileSignedURL,
    FIMCompletion,
    FineTuningJob,
    MistralFile,
    MistralModel,
    ModelDeleted,
    ModerationResult,
    OCRResult,
)

logger = logging.getLogger("toolsconnector.mistral")


class Mistral(BaseConnector):
    """Connect to Mistral AI across its full documented REST surface.

    Supports Bearer token authentication. Pass an API key as
    ``credentials`` when instantiating. Uses the Mistral REST API v1
    (``https://api.mistral.ai/v1``) via direct httpx calls.

    Coverage spans inference (chat, FIM, embeddings, agents), content
    safety (moderations, chat moderations, classifications), document
    understanding (OCR), and the platform-management surface (files,
    fine-tuning jobs, batch jobs, and model management).
    """

    name = "mistral"
    display_name = "Mistral"
    category = ConnectorCategory.AI_ML
    protocol = ProtocolType.REST
    base_url = "https://api.mistral.ai/v1"
    description = (
        "Connect to Mistral AI for chat, embeddings, FIM and agent "
        "completions, content moderation and classification, OCR, plus "
        "file, fine-tuning-job, batch-job, and model management."
    )
    verification_status = "pattern"
    _rate_limit_config = RateLimitSpec(rate=60, period=60, burst=20)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_headers(self) -> dict[str, str]:
        """Build authorization headers for Mistral API requests.

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
        """Execute an authenticated HTTP request against the Mistral API.

        Args:
            method: HTTP method (GET, POST, DELETE, PATCH, etc.).
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

    # ------------------------------------------------------------------
    # Actions -- Chat / FIM / Agents inference
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
        """Create a chat completion using the specified Mistral model.

        Args:
            model: Model ID to use (e.g., ``'mistral-large-latest'``,
                ``'mistral-small-latest'``).
            messages: List of message dicts with ``'role'`` and ``'content'``
                keys (e.g., ``[{"role": "user", "content": "Hi"}]``).
            temperature: Sampling temperature between 0 and 1.
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
        return parsers.parse_chat_completion(data)

    @action("Create a fill-in-the-middle (FIM) code completion")
    async def fim_completion(
        self,
        model: str,
        prompt: str,
        suffix: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> FIMCompletion:
        """Create a fill-in-the-middle code completion.

        FIM lets a code model complete text between a ``prompt`` (the code
        before the cursor) and an optional ``suffix`` (the code after the
        cursor). Useful for inline code generation.

        Args:
            model: Code model ID to use (e.g., ``'codestral-latest'``).
            prompt: The code/text that precedes the insertion point.
            suffix: The code/text that follows the insertion point.
            max_tokens: Maximum number of tokens to generate.

        Returns:
            FIMCompletion with the generated message choices and usage stats.
        """
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
        }
        if suffix is not None:
            payload["suffix"] = suffix
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        data = await self._request("POST", "/fim/completions", json=payload)
        return parsers.parse_fim_completion(data)

    @action("Create an agent completion")
    async def agents_completion(
        self,
        agent_id: str,
        messages: list[dict[str, Any]],
        max_tokens: Optional[int] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        response_format: Optional[dict[str, Any]] = None,
    ) -> AgentsCompletion:
        """Create a completion from a pre-configured Mistral agent.

        Unlike :meth:`chat_completion`, the model and system behaviour are
        defined by the agent referenced by ``agent_id``; you supply only
        the conversation and per-request overrides.

        Args:
            agent_id: The ID of the agent to use for this completion.
            messages: List of message dicts with ``'role'`` and ``'content'``.
            max_tokens: Maximum number of tokens to generate.
            tools: List of tool definitions for function calling.
            response_format: Output format spec, e.g.
                ``{"type": "json_object"}`` or a ``json_schema`` block.

        Returns:
            AgentsCompletion with generated message choices and usage stats.
        """
        payload: dict[str, Any] = {
            "agent_id": agent_id,
            "messages": messages,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if tools is not None:
            payload["tools"] = tools
        if response_format is not None:
            payload["response_format"] = response_format

        data = await self._request("POST", "/agents/completions", json=payload)
        return parsers.parse_agents_completion(data)

    @action("Create text embeddings")
    async def embeddings(
        self,
        model: str,
        input: Union[str, list[str]],
    ) -> Embedding:
        """Create embedding vectors for the given input text(s).

        Args:
            model: Model ID to use (e.g., ``'mistral-embed'``).
            input: A single string or a list of strings to embed.

        Returns:
            Embedding response with vector data and usage statistics.
        """
        payload: dict[str, Any] = {
            "model": model,
            "input": input,
        }
        data = await self._request("POST", "/embeddings", json=payload)
        return parsers.parse_embedding(data)

    # ------------------------------------------------------------------
    # Actions -- Content safety (moderation / classification)
    # ------------------------------------------------------------------

    @action("Run content moderation on text")
    async def moderations(
        self,
        model: str,
        input: Union[str, list[str]],
    ) -> ModerationResult:
        """Classify text against Mistral's content moderation policies.

        Args:
            model: Moderation model ID (e.g., ``'mistral-moderation-latest'``).
            input: A single string or a list of strings to classify.

        Returns:
            ModerationResult with per-category boolean flags and scores
            for the first input.
        """
        payload: dict[str, Any] = {
            "model": model,
            "input": input,
        }
        data = await self._request("POST", "/moderations", json=payload)
        return parsers.parse_moderation(data)

    @action("Run content moderation on a conversation")
    async def chat_moderations(
        self,
        model: str,
        inputs: list[dict[str, Any]],
    ) -> ModerationResult:
        """Moderate a chat conversation against Mistral's safety policies.

        The chat variant scores whole conversations (role/content message
        dicts) rather than raw strings, so policy violations can be judged
        in context.

        Args:
            model: Moderation model ID (e.g., ``'mistral-moderation-latest'``).
            inputs: A list of message dicts with ``'role'`` and ``'content'``,
                or a list of such conversations.

        Returns:
            ModerationResult with per-category boolean flags and scores
            for the first input.
        """
        payload: dict[str, Any] = {
            "model": model,
            "inputs": inputs,
        }
        data = await self._request("POST", "/chat/moderations", json=payload)
        return parsers.parse_moderation(data)

    @action("Classify text with a classifier model")
    async def classifications(
        self,
        model: str,
        input: Union[str, list[str]],
    ) -> ClassificationResult:
        """Classify text using a Mistral classifier model.

        Generalises moderation to arbitrary fine-tuned classifier targets:
        the response carries per-target scores/labels rather than the fixed
        moderation category set.

        Args:
            model: Classifier model ID (e.g., ``'mistral-moderation-latest'``
                or a fine-tuned classifier).
            input: A single string or a list of strings to classify.

        Returns:
            ClassificationResult with per-input, per-target results.
        """
        payload: dict[str, Any] = {
            "model": model,
            "input": input,
        }
        data = await self._request("POST", "/classifications", json=payload)
        return parsers.parse_classification(data)

    # ------------------------------------------------------------------
    # Actions -- OCR
    # ------------------------------------------------------------------

    @action("Run OCR on a document")
    async def ocr_process(
        self,
        model: str,
        document: dict[str, Any],
        pages: Optional[list[int]] = None,
        include_image_base64: Optional[bool] = None,
        image_limit: Optional[int] = None,
        document_annotation_format: Optional[dict[str, Any]] = None,
    ) -> OCRResult:
        """Extract text and structure from a document with Mistral OCR.

        Args:
            model: OCR model ID (e.g., ``'mistral-ocr-latest'``).
            document: The document to process, e.g.
                ``{"type": "document_url", "document_url": "https://..."}``
                or ``{"type": "image_url", "image_url": "https://..."}``.
            pages: Specific zero-indexed page numbers to process.
            include_image_base64: Include extracted images as base64 in the
                response.
            image_limit: Maximum number of images to extract.
            document_annotation_format: Structured-output spec
                (``json_schema``) for extracting fields from the whole
                document.

        Returns:
            OCRResult with one OCRPage of markdown per processed page.
        """
        payload: dict[str, Any] = {
            "model": model,
            "document": document,
        }
        if pages is not None:
            payload["pages"] = pages
        if include_image_base64 is not None:
            payload["include_image_base64"] = include_image_base64
        if image_limit is not None:
            payload["image_limit"] = image_limit
        if document_annotation_format is not None:
            payload["document_annotation_format"] = document_annotation_format

        data = await self._request("POST", "/ocr", json=payload)
        return parsers.parse_ocr_result(data)

    # ------------------------------------------------------------------
    # Actions -- Model management
    # ------------------------------------------------------------------

    @action("List available models", idempotent=True)
    async def list_models(self) -> list[MistralModel]:
        """List all models available to the authenticated account.

        Returns:
            List of MistralModel objects with model metadata.
        """
        data = await self._request("GET", "/models")
        return [parsers.parse_model(m) for m in data.get("data", [])]

    @action("Get a model by ID", idempotent=True)
    async def get_model(self, model_id: str) -> MistralModel:
        """Retrieve metadata about a specific model.

        Args:
            model_id: The model identifier (e.g.,
                ``'ft:mistral-small-latest:...'`` or ``'mistral-large-latest'``).

        Returns:
            MistralModel with full model metadata.
        """
        data = await self._request("GET", f"/models/{model_id}")
        return parsers.parse_model(data)

    @action("Delete a fine-tuned model", dangerous=True)
    async def delete_model(self, model_id: str) -> ModelDeleted:
        """Delete a fine-tuned model.

        Only fine-tuned models owned by the account can be deleted; base
        models cannot.

        Args:
            model_id: The fine-tuned model ID to delete.

        Returns:
            ModelDeleted describing the deletion result.
        """
        data = await self._request("DELETE", f"/models/{model_id}")
        return parsers.parse_model_deleted(data)

    @action("Update a fine-tuned model's name or description")
    async def update_finetuned_model(
        self,
        model_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> MistralModel:
        """Update the name or description of a fine-tuned model.

        Args:
            model_id: The fine-tuned model ID to update.
            name: New display name for the model.
            description: New description for the model.

        Returns:
            The updated MistralModel.
        """
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description

        data = await self._request(
            "PATCH",
            f"/fine_tuning/models/{model_id}",
            json=payload,
        )
        return parsers.parse_model(data)

    @action("Archive a fine-tuned model")
    async def archive_model(self, model_id: str) -> ArchiveModelResult:
        """Archive a fine-tuned model.

        Archiving hides a model from normal listings without deleting it.

        Args:
            model_id: The fine-tuned model ID to archive.

        Returns:
            ArchiveModelResult with ``archived`` set to True.
        """
        data = await self._request(
            "POST",
            f"/fine_tuning/models/{model_id}/archive",
        )
        return parsers.parse_archive_result(data)

    @action("Unarchive a fine-tuned model")
    async def unarchive_model(self, model_id: str) -> ArchiveModelResult:
        """Un-archive a previously archived fine-tuned model.

        Args:
            model_id: The fine-tuned model ID to unarchive.

        Returns:
            ArchiveModelResult with ``archived`` set to False.
        """
        data = await self._request(
            "DELETE",
            f"/fine_tuning/models/{model_id}/archive",
        )
        return parsers.parse_archive_result(data)

    # ------------------------------------------------------------------
    # Actions -- Files
    # ------------------------------------------------------------------

    @action("Upload a file")
    async def upload_file(
        self,
        file_content: bytes,
        purpose: str,
        filename: Optional[str] = None,
    ) -> MistralFile:
        """Upload a file for use with fine-tuning, batch, or OCR.

        The fine-tuning API only accepts ``.jsonl`` files; individual files
        may be up to 512 MB.

        Args:
            file_content: Raw file bytes to upload.
            purpose: Intended purpose (e.g., ``'fine-tune'``, ``'batch'``,
                ``'ocr'``).
            filename: Name for the uploaded file (default: ``"upload.jsonl"``).

        Returns:
            The created MistralFile with file metadata.
        """
        upload_name = filename or "upload.jsonl"

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/files",
                headers={"Authorization": f"Bearer {self._credentials}"},
                files={"file": (upload_name, file_content)},
                data={"purpose": purpose},
            )
            raise_typed_for_status(response, connector=self.name)
            data = response.json()

        return parsers.parse_file(data)

    @action("List uploaded files", idempotent=True)
    async def list_files(
        self,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        purpose: Optional[str] = None,
    ) -> list[MistralFile]:
        """List files that belong to the account's organization.

        Args:
            page: Zero-indexed page number of results to return.
            page_size: Number of files to return per page.
            purpose: Filter by purpose (e.g., ``'fine-tune'``, ``'batch'``).

        Returns:
            List of MistralFile objects with file metadata.
        """
        params: dict[str, Any] = {}
        if page is not None:
            params["page"] = page
        if page_size is not None:
            params["page_size"] = page_size
        if purpose is not None:
            params["purpose"] = purpose

        data = await self._request("GET", "/files", params=params or None)
        return [parsers.parse_file(f) for f in data.get("data", [])]

    @action("Get file metadata by ID", idempotent=True)
    async def get_file(self, file_id: str) -> MistralFile:
        """Retrieve metadata for an uploaded file.

        Args:
            file_id: The file ID to retrieve.

        Returns:
            MistralFile with file metadata.
        """
        data = await self._request("GET", f"/files/{file_id}")
        return parsers.parse_file(data)

    @action("Delete an uploaded file", dangerous=True)
    async def delete_file(self, file_id: str) -> FileDeleted:
        """Delete a file from the Mistral platform.

        Args:
            file_id: The file ID to delete.

        Returns:
            FileDeleted describing the deletion result.
        """
        data = await self._request("DELETE", f"/files/{file_id}")
        return parsers.parse_file_deleted(data)

    @action("Download file content by ID", idempotent=True)
    async def get_file_content(self, file_id: str) -> bytes:
        """Download the raw content of an uploaded file.

        Args:
            file_id: The file ID whose content to download.

        Returns:
            The file content as raw bytes.
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(
                f"{self._base_url}/files/{file_id}/content",
                headers=self._get_headers(),
            )
            raise_typed_for_status(response, connector=self.name)
            return response.content

    @action("Get a temporary signed download URL for a file", idempotent=True)
    async def get_file_signed_url(
        self,
        file_id: str,
        expiry: Optional[int] = None,
    ) -> FileSignedURL:
        """Get a temporary signed URL to download a file.

        Args:
            file_id: The file ID to generate a signed URL for.
            expiry: Hours before the URL expires (1-168, default 24).

        Returns:
            FileSignedURL containing the time-limited download URL.
        """
        params: dict[str, Any] = {}
        if expiry is not None:
            params["expiry"] = expiry

        data = await self._request(
            "GET",
            f"/files/{file_id}/url",
            params=params or None,
        )
        return parsers.parse_signed_url(data)

    # ------------------------------------------------------------------
    # Actions -- Fine-tuning jobs
    # ------------------------------------------------------------------

    @action("Create a fine-tuning job")
    async def create_finetuning_job(
        self,
        model: str,
        hyperparameters: dict[str, Any],
        training_files: Optional[list[dict[str, Any]]] = None,
        validation_files: Optional[list[str]] = None,
        suffix: Optional[str] = None,
        auto_start: Optional[bool] = None,
    ) -> FineTuningJob:
        """Create a new fine-tuning job (queued for processing).

        Args:
            model: The base model to fine-tune (e.g., ``'open-mistral-7b'``).
            hyperparameters: Training hyperparameters, e.g.
                ``{"learning_rate": 0.0001, "training_steps": 10}``.
            training_files: List of training file references, e.g.
                ``[{"file_id": "<uuid>", "weight": 1.0}]``.
            validation_files: List of uploaded validation file IDs.
            suffix: String appended to the fine-tuned model's name.
            auto_start: Whether to start the job immediately after
                validation instead of leaving it queued.

        Returns:
            The created FineTuningJob.
        """
        payload: dict[str, Any] = {
            "model": model,
            "hyperparameters": hyperparameters,
        }
        if training_files is not None:
            payload["training_files"] = training_files
        if validation_files is not None:
            payload["validation_files"] = validation_files
        if suffix is not None:
            payload["suffix"] = suffix
        if auto_start is not None:
            payload["auto_start"] = auto_start

        data = await self._request("POST", "/fine_tuning/jobs", json=payload)
        return parsers.parse_finetuning_job(data)

    @action("List fine-tuning jobs", idempotent=True)
    async def list_finetuning_jobs(
        self,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        model: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[FineTuningJob]:
        """List fine-tuning jobs for the account.

        Args:
            page: Zero-indexed page number of results to return.
            page_size: Number of jobs to return per page.
            model: Filter to jobs fine-tuning this base model.
            status: Filter to jobs in this state (e.g., ``'RUNNING'``,
                ``'SUCCESS'``, ``'FAILED'``).

        Returns:
            List of FineTuningJob objects.
        """
        params: dict[str, Any] = {}
        if page is not None:
            params["page"] = page
        if page_size is not None:
            params["page_size"] = page_size
        if model is not None:
            params["model"] = model
        if status is not None:
            params["status"] = status

        data = await self._request(
            "GET",
            "/fine_tuning/jobs",
            params=params or None,
        )
        return [parsers.parse_finetuning_job(j) for j in data.get("data", [])]

    @action("Get a fine-tuning job by ID", idempotent=True)
    async def get_finetuning_job(self, job_id: str) -> FineTuningJob:
        """Retrieve a fine-tuning job by its UUID.

        Useful for polling a running job's status and metrics.

        Args:
            job_id: The fine-tuning job ID to retrieve.

        Returns:
            FineTuningJob with current status and metadata.
        """
        data = await self._request("GET", f"/fine_tuning/jobs/{job_id}")
        return parsers.parse_finetuning_job(data)

    @action("Start a validated fine-tuning job")
    async def start_finetuning_job(self, job_id: str) -> FineTuningJob:
        """Start a validated, queued fine-tuning job.

        Args:
            job_id: The fine-tuning job ID to start.

        Returns:
            The FineTuningJob with its updated status.
        """
        data = await self._request(
            "POST",
            f"/fine_tuning/jobs/{job_id}/start",
        )
        return parsers.parse_finetuning_job(data)

    @action("Cancel a fine-tuning job", dangerous=True)
    async def cancel_finetuning_job(self, job_id: str) -> FineTuningJob:
        """Request cancellation of a fine-tuning job.

        Args:
            job_id: The fine-tuning job ID to cancel.

        Returns:
            The FineTuningJob with its updated (cancelling/cancelled) status.
        """
        data = await self._request(
            "POST",
            f"/fine_tuning/jobs/{job_id}/cancel",
        )
        return parsers.parse_finetuning_job(data)

    # ------------------------------------------------------------------
    # Actions -- Batch jobs
    # ------------------------------------------------------------------

    @action("Create a batch job")
    async def create_batch_job(
        self,
        endpoint: str,
        input_files: Optional[list[str]] = None,
        requests: Optional[list[dict[str, Any]]] = None,
        model: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
        timeout_hours: Optional[int] = None,
    ) -> BatchJob:
        """Create a new batch inference job (queued for processing).

        Provide either ``input_files`` (uploaded ``.jsonl`` batch files) or
        inline ``requests``.

        Args:
            endpoint: Target inference endpoint for the batch, e.g.
                ``'/v1/chat/completions'``, ``'/v1/embeddings'``,
                ``'/v1/moderations'``, or ``'/v1/ocr'``.
            input_files: List of uploaded batch input file IDs.
            requests: Inline list of request objects to batch.
            model: The model to use for batch inference (one per batch).
            metadata: Arbitrary string metadata to attach to the job.
            timeout_hours: Timeout in hours for the batch job.

        Returns:
            The created BatchJob.
        """
        payload: dict[str, Any] = {"endpoint": endpoint}
        if input_files is not None:
            payload["input_files"] = input_files
        if requests is not None:
            payload["requests"] = requests
        if model is not None:
            payload["model"] = model
        if metadata is not None:
            payload["metadata"] = metadata
        if timeout_hours is not None:
            payload["timeout_hours"] = timeout_hours

        data = await self._request("POST", "/batch/jobs", json=payload)
        return parsers.parse_batch_job(data)

    @action("List batch jobs", idempotent=True)
    async def list_batch_jobs(
        self,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        model: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[BatchJob]:
        """List batch jobs for the account.

        Args:
            page: Zero-indexed page number of results to return.
            page_size: Number of jobs to return per page.
            model: Filter to batch jobs using this model.
            status: Filter to jobs in this state (e.g., ``'RUNNING'``,
                ``'SUCCESS'``, ``'FAILED'``).

        Returns:
            List of BatchJob objects.
        """
        params: dict[str, Any] = {}
        if page is not None:
            params["page"] = page
        if page_size is not None:
            params["page_size"] = page_size
        if model is not None:
            params["model"] = model
        if status is not None:
            params["status"] = status

        data = await self._request(
            "GET",
            "/batch/jobs",
            params=params or None,
        )
        return [parsers.parse_batch_job(j) for j in data.get("data", [])]

    @action("Get a batch job by ID", idempotent=True)
    async def get_batch_job(self, job_id: str) -> BatchJob:
        """Retrieve a batch job by its UUID.

        Useful for polling a running batch's progress counts.

        Args:
            job_id: The batch job ID to retrieve.

        Returns:
            BatchJob with current status and per-request counts.
        """
        data = await self._request("GET", f"/batch/jobs/{job_id}")
        return parsers.parse_batch_job(data)

    @action("Cancel a batch job", dangerous=True)
    async def cancel_batch_job(self, job_id: str) -> BatchJob:
        """Request cancellation of a batch job.

        Args:
            job_id: The batch job ID to cancel.

        Returns:
            The BatchJob with its updated (cancelling/cancelled) status.
        """
        data = await self._request(
            "POST",
            f"/batch/jobs/{job_id}/cancel",
        )
        return parsers.parse_batch_job(data)

    @action("Delete a batch job", dangerous=True)
    async def delete_batch_job(self, job_id: str) -> BatchJobDeleted:
        """Delete a batch job.

        Args:
            job_id: The batch job ID to delete.

        Returns:
            BatchJobDeleted describing the deletion result.
        """
        data = await self._request("DELETE", f"/batch/jobs/{job_id}")
        return parsers.parse_batch_job_deleted(data)
