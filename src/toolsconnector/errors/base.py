"""Base exception class for all ToolsConnector errors."""

from __future__ import annotations

import json
from typing import Any


class ToolsConnectorError(Exception):
    """Base exception for all ToolsConnector errors.

    Every error carries structured metadata that is useful for both
    human debugging and programmatic retry / routing logic in AI agents.

    Attributes:
        message: Human-readable description of what went wrong.
        connector: Name of the connector that raised the error (e.g. ``"gmail"``).
        action: Name of the action that was executing, if applicable.
        code: Machine-readable error code (should match :class:`ErrorCode` values).
        retry_eligible: Whether the caller may retry this request.
        retry_after_seconds: Suggested minimum wait before retrying.
        suggestion: Actionable hint for the developer or agent.
        details: Arbitrary extra context (must be JSON-serializable).
        upstream_status: HTTP status code from the upstream API, if any.
    """

    def __init__(
        self,
        message: str,
        *,
        connector: str = "",
        action: str | None = None,
        code: str = "UNKNOWN",
        retry_eligible: bool = False,
        retry_after_seconds: float | None = None,
        suggestion: str | None = None,
        details: dict[str, Any] | None = None,
        upstream_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.connector = connector
        self.action = action
        self.code = code
        self.retry_eligible = retry_eligible
        self.retry_after_seconds = retry_after_seconds
        self.suggestion = suggestion
        self.details = details or {}
        self.upstream_status = upstream_status

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary of the error."""
        result: dict[str, Any] = {
            "error": type(self).__name__,
            "code": self.code,
            "message": self.message,
            "connector": self.connector,
            "retry_eligible": self.retry_eligible,
        }
        if self.action is not None:
            result["action"] = self.action
        if self.retry_after_seconds is not None:
            result["retry_after_seconds"] = self.retry_after_seconds
        if self.suggestion is not None:
            result["suggestion"] = self.suggestion
        if self.details:
            result["details"] = self.details
        if self.upstream_status is not None:
            result["upstream_status"] = self.upstream_status
        return result

    def to_json(self) -> str:
        """Return a compact JSON string of :meth:`to_dict`."""
        return json.dumps(self.to_dict(), default=str)

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        parts = [f"[{self.code}]"]
        if self.connector:
            parts.append(f"({self.connector})")
        parts.append(self.message)
        if self.suggestion:
            parts.append(f"| Suggestion: {self.suggestion}")
        return " ".join(parts)

    def __repr__(self) -> str:
        cls = type(self).__name__
        return (
            f"{cls}(message={self.message!r}, code={self.code!r}, "
            f"connector={self.connector!r})"
        )
