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

    # ------------------------------------------------------------------
    # Actions -- Batches
    # ------------------------------------------------------------------

    @action("Create a message batch", dangerous=True)
    async def create_batch(
        self, requests: list[dict[str, Any]],
    ) -> AnthropicBatch:
        """Create a Message Batch for async processing.

        Args:
            requests: List of batch request dicts, each with
                ``custom_id`` and ``params`` keys.

        Returns:
            The created AnthropicBatch.
        """
        resp = await self._request(
            "POST", "/v1/messages/batches",
            json_body={"requests": requests},
        )
        data = resp.json()
        return AnthropicBatch(
            id=data.get("id", ""),
            type=data.get("type", "message_batch"),
            processing_status=data.get("processing_status"),
            request_counts=data.get("request_counts"),
            ended_at=data.get("ended_at"),
            created_at=data.get("created_at"),
            expires_at=data.get("expires_at"),
        )

    @action("Get a message batch by ID")
    async def get_batch(self, batch_id: str) -> AnthropicBatch:
        """Retrieve a Message Batch by ID.

        Args:
            batch_id: The batch ID.

        Returns:
            AnthropicBatch with current status.
        """
        resp = await self._request(
            "GET", f"/v1/messages/batches/{batch_id}",
        )
        data = resp.json()
        return AnthropicBatch(
            id=data.get("id", ""),
            type=data.get("type", "message_batch"),
            processing_status=data.get("processing_status"),
            request_counts=data.get("request_counts"),
            ended_at=data.get("ended_at"),
            created_at=data.get("created_at"),
            expires_at=data.get("expires_at"),
        )

    @action("List message batches")
    async def list_batches(
        self, limit: Optional[int] = None,
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
        resp = await self._request(
            "GET", "/v1/messages/batches", params=params or None,
        )
        data = resp.json()
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
