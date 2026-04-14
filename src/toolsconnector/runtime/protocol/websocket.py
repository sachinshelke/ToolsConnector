"""WebSocket protocol adapter.

Manages a persistent WebSocket connection for real-time bidirectional
communication (e.g. Slack RTM, Discord Gateway) and normalizes every
message into a :class:`ProtocolResponse`.
"""

from __future__ import annotations

import json as _json
from typing import Any, Optional

from .base import ProtocolResponse


class WebSocketAdapter:
    """Protocol adapter for WebSocket APIs.

    Manages a persistent WebSocket connection for real-time
    bidirectional communication.

    Args:
        url: The ``ws://`` or ``wss://`` endpoint URL.
        headers: Additional headers sent during the handshake
            (e.g. authorization tokens).
    """

    def __init__(
        self,
        url: str,
        headers: Optional[dict[str, str]] = None,
    ) -> None:
        self._url = url
        self._headers: dict[str, str] = headers or {}
        self._connection: Optional[Any] = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Establish the WebSocket connection.

        Raises:
            ImportError: If the ``websockets`` package is not installed.
        """
        try:
            import websockets  # type: ignore[import-untyped]
        except ImportError:
            raise ImportError(
                "WebSocket adapter requires 'websockets'. "
                'Install with: pip install "toolsconnector[websocket]"'
            )

        self._connection = await websockets.connect(
            self._url,
            additional_headers=self._headers,
        )

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
        """Send a message and wait for the next response.

        For WebSocket, *operation* is the message type / event name and
        *body* supplies additional payload fields.

        Args:
            operation: Message type or event name included as the
                ``"type"`` field in the outgoing JSON frame.
            method: Ignored -- not applicable to WebSocket.
            params: Ignored -- not applicable to WebSocket.
            body: Additional payload fields merged into the outgoing
                JSON frame.
            headers: Ignored -- headers are set at connect time.

        Returns:
            A :class:`ProtocolResponse` whose *data* is the parsed JSON
            message (or a ``{"raw": ...}`` fallback when the response
            is not valid JSON).
        """
        if self._connection is None:
            await self.connect()

        message = _json.dumps({"type": operation, **(body or {})})
        await self._connection.send(message)

        response_raw = await self._connection.recv()

        data = self._parse_frame(response_raw)
        raw_bytes = (
            response_raw.encode("utf-8")
            if isinstance(response_raw, str)
            else response_raw
        )

        return ProtocolResponse(
            data=data,
            raw=raw_bytes,
            metadata={"websocket": True},
        )

    async def close(self) -> None:
        """Close the WebSocket connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None

    # ------------------------------------------------------------------
    # Extra helpers for streaming use-cases
    # ------------------------------------------------------------------

    async def send(self, message: str) -> None:
        """Send a raw message without waiting for a response.

        Args:
            message: The string payload to send over the socket.
        """
        if self._connection is None:
            await self.connect()
        await self._connection.send(message)

    async def receive(self) -> ProtocolResponse:
        """Receive the next message from the server.

        Returns:
            A :class:`ProtocolResponse` with the parsed (or raw)
            message data.
        """
        if self._connection is None:
            await self.connect()

        raw = await self._connection.recv()
        data = self._parse_frame(raw)
        raw_bytes = (
            raw.encode("utf-8") if isinstance(raw, str) else raw
        )

        return ProtocolResponse(
            data=data,
            raw=raw_bytes,
            metadata={"websocket": True},
        )

    # ------------------------------------------------------------------
    # Context-manager support
    # ------------------------------------------------------------------

    async def __aenter__(self) -> WebSocketAdapter:
        await self.connect()
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_frame(raw: Any) -> Any:
        """Attempt to parse a WebSocket frame as JSON.

        Args:
            raw: The raw frame received from the socket (``str`` or
                ``bytes``).

        Returns:
            Parsed JSON data, or a ``{"raw": ...}`` fallback dict when
            the frame is not valid JSON.
        """
        text = raw if isinstance(raw, str) else raw.decode("utf-8", errors="replace")
        try:
            return _json.loads(text)
        except (ValueError, UnicodeDecodeError):
            return {"raw": text}
