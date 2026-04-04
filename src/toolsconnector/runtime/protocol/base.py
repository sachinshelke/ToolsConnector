"""Base protocol adapter contract and normalized response model.

Defines the :class:`ProtocolAdapter` protocol that every protocol-level
adapter must satisfy, along with the :class:`ProtocolResponse` model used
to return normalized results regardless of the underlying wire protocol
(REST, GraphQL, gRPC, etc.).
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class ProtocolResponse(BaseModel):
    """Normalized response produced by any :class:`ProtocolAdapter`.

    Attributes:
        status: Protocol-level status code (e.g. HTTP status).
        data: Deserialized response payload (typically ``dict`` or ``list``
            after JSON parsing, but may be any type).
        raw: Original response body bytes, preserved for callers that need
            access to the unparsed content.
        headers: Response headers as a flat string-to-string mapping.
        metadata: Extra protocol-specific metadata (pagination cursors,
            rate-limit info, etc.).
    """

    status: Optional[int] = None
    data: Any = None
    raw: Optional[bytes] = None
    headers: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}


@runtime_checkable
class ProtocolAdapter(Protocol):
    """Contract for translating high-level operations into wire calls.

    A protocol adapter sits between the connector action layer and the
    raw :class:`~toolsconnector.runtime.transport.base.Transport`.  It
    knows *how* to speak a specific wire protocol (REST, GraphQL, ...)
    and normalizes every response into a :class:`ProtocolResponse`.
    """

    async def request(
        self,
        operation: str,
        *,
        method: Optional[str] = None,
        params: Optional[dict[str, Any]] = None,
        body: Any = None,
        headers: Optional[dict[str, str]] = None,
    ) -> ProtocolResponse:
        """Execute a named operation.

        Args:
            operation: Logical operation identifier.  For REST adapters
                this is typically the URL path; for GraphQL it could be
                the query name.
            method: Optional HTTP method override (REST-specific).
            params: Query-string or operation parameters.
            body: Request body -- will be JSON-serialized for REST.
            headers: Per-request header overrides.

        Returns:
            A :class:`ProtocolResponse` with the normalized result.
        """
        ...

    async def close(self) -> None:
        """Release resources held by the adapter and its transport."""
        ...
