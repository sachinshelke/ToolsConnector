"""Base transport protocol and response model.

Defines the ``Transport`` protocol that all transport implementations must
satisfy, along with the ``TransportResponse`` data class returned by every
transport call.

The protocol is :func:`~typing.runtime_checkable` so consumers can use
``isinstance`` checks against concrete implementations.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class TransportResponse(BaseModel):
    """Raw response returned by a :class:`Transport` implementation.

    Attributes:
        status_code: HTTP (or protocol-equivalent) status code.
        headers: Response headers as a flat string-to-string mapping.
        body: Raw response body bytes.
    """

    status_code: int
    headers: dict[str, str] = Field(default_factory=dict)
    body: bytes = b""

    model_config = {"frozen": True}


@runtime_checkable
class Transport(Protocol):
    """Low-level I/O contract for sending bytes over the wire.

    Implementations must be async-capable.  The constructor signature is
    not constrained by this protocol -- only ``request`` and ``close`` are
    required.
    """

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[dict[str, str]] = None,
        params: Optional[dict[str, Any]] = None,
        json: Any = None,
        content: Optional[bytes] = None,
        timeout: Optional[float] = None,
    ) -> TransportResponse:
        """Send a request and return a :class:`TransportResponse`.

        Args:
            method: HTTP method (``GET``, ``POST``, etc.).
            url: Fully-qualified or relative URL.
            headers: Extra headers merged with any defaults.
            params: URL query-string parameters.
            json: JSON-serializable body (mutually exclusive with *content*).
            content: Raw bytes body (mutually exclusive with *json*).
            timeout: Per-request timeout in seconds, overriding the default.

        Returns:
            A populated :class:`TransportResponse`.
        """
        ...

    async def close(self) -> None:
        """Release underlying connections and resources."""
        ...
