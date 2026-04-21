"""GraphQL protocol adapter.

Translates high-level connector calls into GraphQL queries and mutations
posted to a single endpoint, and normalizes every response into a
:class:`ProtocolResponse`.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx

from toolsconnector.errors import ValidationError

from .base import ProtocolResponse


class GraphQLAdapter:
    """Protocol adapter for GraphQL APIs.

    Translates connector calls into GraphQL queries/mutations
    posted to a single endpoint.

    Args:
        endpoint_url: Full URL to the GraphQL endpoint
            (e.g. ``"https://api.linear.app/graphql"``).
        headers: Default headers sent with every request (auth,
            content-type, etc.).
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        endpoint_url: str,
        headers: Optional[dict[str, str]] = None,
        timeout: float = 30.0,
    ) -> None:
        self._endpoint = endpoint_url
        self._headers: dict[str, str] = headers or {}
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Lazily create the underlying HTTP client.

        Returns:
            The shared :class:`httpx.AsyncClient` instance.
        """
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    # ------------------------------------------------------------------
    # ProtocolAdapter interface
    # ------------------------------------------------------------------

    async def request(
        self,
        operation: str,
        *,
        method: Optional[str] = None,
        params: Optional[dict[str, Any]] = None,
        body: Any = None,
        headers: Optional[dict[str, str]] = None,
    ) -> ProtocolResponse:
        """Execute a GraphQL query or mutation.

        Args:
            operation: The GraphQL query or mutation string.
            method: Ignored -- GraphQL always uses ``POST``.
            params: Ignored -- use *body* for GraphQL variables.
            body: Variables ``dict`` forwarded as the ``"variables"``
                field in the JSON payload.
            headers: Additional headers merged with the defaults
                for this single request.

        Returns:
            A :class:`ProtocolResponse` with *data* set to the
            ``"data"`` field of the GraphQL JSON response.

        Raises:
            toolsconnector.errors.ValidationError: When the response
                contains a non-empty ``"errors"`` array.
        """
        client = await self._ensure_client()

        payload: dict[str, Any] = {"query": operation}
        if body:
            payload["variables"] = body

        merged_headers = {**self._headers, **(headers or {})}
        merged_headers.setdefault("Content-Type", "application/json")

        response = await client.post(
            self._endpoint,
            json=payload,
            headers=merged_headers,
        )
        response.raise_for_status()
        result = response.json()

        # Surface GraphQL-level errors as a ValidationError.
        if "errors" in result and result["errors"]:
            error_msgs = "; ".join(e.get("message", "Unknown") for e in result["errors"])
            raise ValidationError(
                f"GraphQL error: {error_msgs}",
                details={"graphql_errors": result["errors"]},
            )

        return ProtocolResponse(
            status=response.status_code,
            data=result.get("data"),
            raw=response.content,
            headers=dict(response.headers),
            metadata={"extensions": result.get("extensions", {})},
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Context-manager support
    # ------------------------------------------------------------------

    async def __aenter__(self) -> GraphQLAdapter:
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.close()
