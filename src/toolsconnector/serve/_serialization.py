"""Result serialization for serve layer output.

Converts any action result to a JSON string suitable for MCP, CLI,
and REST output. Handles Pydantic models, lists, dicts, primitives,
and falls back to ``str()`` for unknown types.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel


def serialize_result(result: Any) -> str:
    """Convert any action result to a JSON string.

    Handles:
        - ``None`` -- ``'{"status": "ok"}'``
        - Pydantic ``BaseModel`` -- ``model_dump_json()``
        - ``list`` -- JSON array (each item serialized)
        - ``dict`` -- ``json.dumps``
        - Primitives (``str``, ``int``, ``float``, ``bool``) -- wrapped
        - Anything else -- ``str()`` fallback

    Args:
        result: The raw return value from a connector action.

    Returns:
        A JSON string ready for transport.
    """
    if result is None:
        return json.dumps({"status": "ok"})

    if isinstance(result, BaseModel):
        return result.model_dump_json(indent=2)

    if isinstance(result, list):
        serialized: list[Any] = []
        for item in result:
            if isinstance(item, BaseModel):
                serialized.append(item.model_dump())
            else:
                serialized.append(item)
        return json.dumps(serialized, indent=2, default=str)

    if isinstance(result, dict):
        return json.dumps(result, indent=2, default=str)

    if isinstance(result, (str, int, float, bool)):
        return json.dumps({"result": result})

    # Fallback for unknown types
    return json.dumps({"result": str(result)}, default=str)


def serialize_error(error: Exception) -> str:
    """Serialize an error to a JSON string.

    If the error has a ``to_dict()`` method (i.e., a
    ``ToolsConnectorError`` subclass), uses that for structured output.
    Otherwise, falls back to basic ``{error, message}`` format.

    Args:
        error: The exception to serialize.

    Returns:
        A JSON string with error details.
    """
    if hasattr(error, "to_dict"):
        return json.dumps(error.to_dict(), indent=2, default=str)

    return json.dumps(
        {
            "error": type(error).__name__,
            "message": str(error),
        },
        indent=2,
    )
