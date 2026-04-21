"""Anthropic connector -- create messages, count tokens, and list models.

Uses httpx for direct HTTP calls against the Anthropic REST API v1.
Expects an API key passed as ``credentials``.
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

from .types import (
    AnthropicBatch,
    AnthropicMessage,
    AnthropicModel,
    ContentBlock,
    TokenCount,
    Usage,
)

logger = logging.getLogger("toolsconnector.anthropic")

# Anthropic API version header
_ANTHROPIC_VERSION = "2023-06-01"


class Anthropic(BaseConnector):
    """Connect to Anthropic for message creation, token counting, and model listing.

    Supports API key authentication via the ``x-api-key`` header.
    Pass an API key as ``credentials`` when instantiating. Uses the
    Anthropic REST API v1 via direct httpx calls.
    """

    name = "anthropic"
    display_name = "Anthropic"
    category = ConnectorCategory.AI_ML
    protocol = ProtocolType.REST
    base_url = "https://api.anthropic.com/v1"
    description = (
        "Connect to Anthropic for creating messages with Claude models, "
        "counting tokens, and listing available models."
    )
    _rate_limit_config = RateLimitSpec(rate=60, period=60, burst=20)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_headers(self) -> dict[str, str]:
        """Build authentication headers for Anthropic API requests.

        Returns:
            Dict with x-api-key, anthropic-version, and content-type headers.
        """
        return {
            "x-api-key": str(self._credentials),
            "anthropic-version": _ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute an authenticated HTTP request against the Anthropic API.

        Args:
            method: HTTP method (GET, POST, etc.).
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

    @action("Create a message with Claude")
    async def create_message(
        self,
        model: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> AnthropicMessage:
        """Create a message using the specified Claude model.

        Args:
            model: Model ID to use (e.g., 'claude-sonnet-4-20250514').
            messages: List of message dicts with 'role' and 'content' keys.
            max_tokens: Maximum number of tokens to generate.
            system: System prompt to set context for the conversation.
            temperature: Sampling temperature between 0 and 1.
            tools: List of tool definitions for function calling.

        Returns:
            AnthropicMessage with generated content blocks and usage stats.
        """
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if system is not None:
            payload["system"] = system
        if temperature is not None:
            payload["temperature"] = temperature
        if tools is not None:
            payload["tools"] = tools

        data = await self._request("POST", "/messages", json=payload)

        content_blocks = [
            ContentBlock(
                type=block.get("type", "text"),
                text=block.get("text"),
                id=block.get("id"),
                name=block.get("name"),
                input=block.get("input"),
                tool_use_id=block.get("tool_use_id"),
                content=block.get("content") if isinstance(block.get("content"), str) else None,
            )
            for block in data.get("content", [])
        ]

        usage_data = data.get("usage")
        usage = (
            Usage(
                input_tokens=usage_data.get("input_tokens", 0),
                output_tokens=usage_data.get("output_tokens", 0),
                cache_creation_input_tokens=usage_data.get("cache_creation_input_tokens"),
                cache_read_input_tokens=usage_data.get("cache_read_input_tokens"),
            )
            if usage_data
            else None
        )

        return AnthropicMessage(
            id=data.get("id", ""),
            type=data.get("type", "message"),
            role=data.get("role", "assistant"),
            content=content_blocks,
            model=data.get("model", ""),
            stop_reason=data.get("stop_reason"),
            stop_sequence=data.get("stop_sequence"),
            usage=usage,
        )

    @action("Count tokens for a message", idempotent=True)
    async def count_tokens(
        self,
        model: str,
        messages: list[dict[str, Any]],
    ) -> TokenCount:
        """Count the number of tokens in a message payload.

        Useful for estimating costs and ensuring messages fit within
        model context windows before sending.

        Args:
            model: Model ID to count tokens for.
            messages: List of message dicts with 'role' and 'content' keys.

        Returns:
            TokenCount with the number of input tokens.
        """
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }

        data = await self._request("POST", "/messages/count_tokens", json=payload)

        return TokenCount(
            input_tokens=data.get("input_tokens", 0),
        )

    @action("List available Anthropic models", idempotent=True)
    async def list_models(self) -> list[AnthropicModel]:
        """List all models available through the Anthropic API.

        Returns:
            List of AnthropicModel objects with model metadata.
        """
        data = await self._request("GET", "/models")

        return [
            AnthropicModel(
                id=m.get("id", ""),
                display_name=m.get("display_name", ""),
                type=m.get("type", "model"),
                created_at=m.get("created_at"),
            )
            for m in data.get("data", [])
        ]

    @action("Get a model by ID", idempotent=True)
    async def get_model(self, model_id: str) -> AnthropicModel:
        """Retrieve details about a specific Anthropic model.

        Args:
            model_id: The model identifier (e.g., ``'claude-sonnet-4-20250514'``).

        Returns:
            AnthropicModel with model metadata and capabilities.
        """
        data = await self._request("GET", f"/models/{model_id}")

        return AnthropicModel(
            id=data.get("id", ""),
            display_name=data.get("display_name", ""),
            type=data.get("type", "model"),
            created_at=data.get("created_at"),
        )

    # ------------------------------------------------------------------
    # Actions -- Batches
    # ------------------------------------------------------------------

    @action("Create a message batch", dangerous=True)
    async def create_batch(
        self,
        requests: list[dict[str, Any]],
    ) -> AnthropicBatch:
        """Create a Message Batch for async processing.

        Sends up to 100,000 message requests for background processing
        at 50% reduced cost.

        Args:
            requests: List of batch request dicts, each with
                ``custom_id`` and ``params`` keys.

        Returns:
            The created AnthropicBatch.
        """
        data = await self._request(
            "POST",
            "/messages/batches",
            json={"requests": requests},
        )
        return AnthropicBatch(
            id=data.get("id", ""),
            type=data.get("type", "message_batch"),
            processing_status=data.get("processing_status"),
            request_counts=data.get("request_counts"),
            ended_at=data.get("ended_at"),
            created_at=data.get("created_at"),
            expires_at=data.get("expires_at"),
        )

    @action("Get a message batch by ID", idempotent=True)
    async def get_batch(self, batch_id: str) -> AnthropicBatch:
        """Retrieve a Message Batch by ID.

        Can be used to poll for batch completion status.

        Args:
            batch_id: The batch ID.

        Returns:
            AnthropicBatch with current status.
        """
        data = await self._request("GET", f"/messages/batches/{batch_id}")
        return AnthropicBatch(
            id=data.get("id", ""),
            type=data.get("type", "message_batch"),
            processing_status=data.get("processing_status"),
            request_counts=data.get("request_counts"),
            ended_at=data.get("ended_at"),
            created_at=data.get("created_at"),
            expires_at=data.get("expires_at"),
        )

    @action("List message batches", idempotent=True)
    async def list_batches(
        self,
        limit: Optional[int] = None,
    ) -> list[AnthropicBatch]:
        """List Message Batches.

        Args:
            limit: Maximum number of batches to return.

        Returns:
            List of AnthropicBatch objects.
        """
        params: dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit

        data = await self._request(
            "GET",
            "/messages/batches",
            params=params or None,
        )
        return [
            AnthropicBatch(
                id=b.get("id", ""),
                type=b.get("type", "message_batch"),
                processing_status=b.get("processing_status"),
                request_counts=b.get("request_counts"),
                ended_at=b.get("ended_at"),
                created_at=b.get("created_at"),
                expires_at=b.get("expires_at"),
            )
            for b in data.get("data", [])
        ]

    @action("Cancel a message batch")
    async def cancel_batch(self, batch_id: str) -> AnthropicBatch:
        """Cancel a Message Batch that is currently in progress.

        Initiates best-effort cancellation. Already-completed requests
        within the batch will not be undone.

        Args:
            batch_id: The batch ID to cancel.

        Returns:
            AnthropicBatch with updated status reflecting cancellation.
        """
        data = await self._request(
            "POST",
            f"/messages/batches/{batch_id}/cancel",
        )
        return AnthropicBatch(
            id=data.get("id", ""),
            type=data.get("type", "message_batch"),
            processing_status=data.get("processing_status"),
            request_counts=data.get("request_counts"),
            ended_at=data.get("ended_at"),
            created_at=data.get("created_at"),
            expires_at=data.get("expires_at"),
        )

    @action("Get message batch results", idempotent=True)
    async def get_batch_results(self, batch_id: str) -> list[dict[str, Any]]:
        """Retrieve the results of a completed Message Batch.

        Returns the JSONL results as a list of dicts. Each result
        contains a ``custom_id`` matching the original request and
        a ``result`` with the message response or error.

        Args:
            batch_id: The batch ID whose results to retrieve.

        Returns:
            List of result dicts with ``custom_id`` and ``result`` keys.
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(
                f"{self._base_url}/messages/batches/{batch_id}/results",
                headers=self._get_headers(),
            )
            response.raise_for_status()
            # Results are returned as JSONL (one JSON object per line)
            import json

            results: list[dict[str, Any]] = []
            for line in response.text.strip().splitlines():
                line = line.strip()
                if line:
                    results.append(json.loads(line))
            return results

    @action("Delete a message batch", dangerous=True)
    async def delete_message_batch(self, batch_id: str) -> None:
        """Permanently delete a Message Batch and its results.

        This action is irreversible. The batch must have finished
        processing (``ended``) before it can be deleted.

        Args:
            batch_id: The batch ID to delete.
        """
        await self._request("DELETE", f"/messages/batches/{batch_id}")

    # ------------------------------------------------------------------
    # Actions — Files (Beta)
    # ------------------------------------------------------------------

    @action("Upload a file for use across API calls", dangerous=True)
    async def upload_file(
        self,
        content: str,
        filename: str,
        media_type: str = "text/plain",
    ) -> dict[str, Any]:
        """Upload a file to use in subsequent Messages API calls.

        Files can be referenced across multiple conversations without
        re-uploading. Requires the ``anthropic-beta: files-api-2025-04-14``
        header.

        Args:
            content: The file content as a string.
            filename: Name for the uploaded file.
            media_type: MIME type (e.g., 'text/plain', 'application/pdf').

        Returns:
            Dict with file id, filename, media_type, size_bytes.
        """
        import base64

        encoded = base64.standard_b64encode(content.encode("utf-8")).decode("ascii")
        data = await self._request(
            "POST",
            "/files",
            json={
                "filename": filename,
                "media_type": media_type,
                "data": encoded,
            },
            headers={"anthropic-beta": "files-api-2025-04-14"},
        )
        return data

    @action("List uploaded files")
    async def list_files(
        self,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """List files uploaded to the API.

        Args:
            limit: Maximum number of files to return.

        Returns:
            List of file dicts with id, filename, media_type, size.
        """
        data = await self._request(
            "GET",
            "/files",
            params={"limit": limit},
            headers={"anthropic-beta": "files-api-2025-04-14"},
        )
        return data.get("data", [])

    @action("Get a file by ID")
    async def get_file(self, file_id: str) -> dict[str, Any]:
        """Retrieve metadata for an uploaded file.

        Args:
            file_id: The file ID.

        Returns:
            File dict with id, filename, media_type, size_bytes.
        """
        data = await self._request(
            "GET",
            f"/files/{file_id}",
            headers={"anthropic-beta": "files-api-2025-04-14"},
        )
        return data

    @action("Delete an uploaded file", dangerous=True)
    async def delete_file(self, file_id: str) -> None:
        """Delete an uploaded file.

        Args:
            file_id: The file ID to delete.
        """
        await self._request(
            "DELETE",
            f"/files/{file_id}",
            headers={"anthropic-beta": "files-api-2025-04-14"},
        )
