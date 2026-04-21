"""REST protocol adapter.

Translates high-level operation names into RESTful HTTP calls via an
underlying :class:`~toolsconnector.runtime.transport.base.Transport`
and normalizes every response into a :class:`ProtocolResponse`.
"""

from __future__ import annotations

import json as _json
from typing import Any, Optional

from toolsconnector.runtime.transport.base import Transport

from .base import ProtocolResponse

_JSON_CONTENT_TYPES = frozenset(
    {
        "application/json",
        "application/vnd.api+json",
        "application/problem+json",
    }
)

_DEFAULT_METHOD = "GET"


class RESTAdapter:
    """Protocol adapter for RESTful HTTP APIs.

    The adapter maps a logical *operation* string to a URL path, delegates
    the actual I/O to a :class:`Transport`, and parses the response body
    when the content type indicates JSON.

    Args:
        transport: A :class:`Transport` implementation used for raw HTTP.
        base_path: Optional path prefix prepended to every operation
            (e.g. ``"/v2"``).  A leading ``/`` is added automatically
            if missing.
    """

    def __init__(
        self,
        transport: Transport,
        *,
        base_path: str = "",
    ) -> None:
        self._transport = transport
        self._base_path = base_path.rstrip("/") if base_path else ""

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
        """Execute a REST operation.

        Args:
            operation: URL path segment for this operation.  Combined with
                *base_path* to form the full request URL -- e.g. an
                operation of ``"/users/42"`` with a base path of ``"/v2"``
                yields ``"/v2/users/42"``.
            method: HTTP method.  Defaults to ``GET`` when *body* is
                ``None``, otherwise ``POST``.
            params: URL query-string parameters forwarded to the transport.
            body: Request body.  If not ``None`` it is sent as JSON via
                the transport's *json* parameter.
            headers: Per-request header overrides.

        Returns:
            A :class:`ProtocolResponse` with *data* populated from the
            parsed JSON body (when applicable) and *raw* always set to
            the original bytes.

        Raises:
            toolsconnector.errors.TransportError: Re-raised from the
                transport layer on any I/O failure.
        """
        effective_method = method or (_DEFAULT_METHOD if body is None else "POST")
        url = self._build_url(operation)

        transport_response = await self._transport.request(
            effective_method,
            url,
            headers=headers,
            params=params,
            json=body,
        )

        data = self._parse_body(
            transport_response.body,
            transport_response.headers,
        )

        return ProtocolResponse(
            status=transport_response.status_code,
            data=data,
            raw=transport_response.body,
            headers=transport_response.headers,
        )

    async def close(self) -> None:
        """Close the underlying transport."""
        await self._transport.close()

    # ------------------------------------------------------------------
    # Context-manager support
    # ------------------------------------------------------------------

    async def __aenter__(self) -> RESTAdapter:
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_url(self, operation: str) -> str:
        """Combine *base_path* and *operation* into a URL path.

        Args:
            operation: The operation path segment.

        Returns:
            The combined URL path string.
        """
        op = operation if operation.startswith("/") else f"/{operation}"
        if self._base_path:
            return f"{self._base_path}{op}"
        return op

    @staticmethod
    def _parse_body(
        raw: bytes,
        headers: dict[str, str],
    ) -> Any:
        """Attempt to deserialize *raw* as JSON based on content type.

        Falls back to returning the raw bytes when the content type is
        not JSON or when parsing fails.

        Args:
            raw: The raw response body bytes.
            headers: Response headers used for content-type detection.

        Returns:
            Parsed JSON data (``dict`` / ``list`` / scalar) or the
            original *raw* bytes if parsing is not applicable.
        """
        if not raw:
            return None

        content_type = headers.get("content-type", "")
        # Extract the media-type portion before any parameters (charset, etc.)
        media_type = content_type.split(";", 1)[0].strip().lower()

        if media_type in _JSON_CONTENT_TYPES:
            try:
                return _json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                # Malformed JSON -- return raw bytes so the caller can
                # inspect the original payload.
                return raw

        return raw
