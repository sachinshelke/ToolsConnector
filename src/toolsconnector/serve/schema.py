"""Multi-framework schema generators.

Generates tool definitions for OpenAI, Anthropic, Gemini, and LangChain
from ToolEntry objects. All generators read from the same input_schema
(JSON Schema) — they just wrap it in different platform-specific formats.
"""

from __future__ import annotations

from typing import Any

from toolsconnector.serve._filtering import ToolEntry


def to_openai_schema(entry: ToolEntry) -> dict[str, Any]:
    """Generate OpenAI function calling definition for a tool.

    Format: {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}

    Args:
        entry: ToolEntry describing the tool.

    Returns:
        OpenAI-compatible function calling definition.
    """
    return {
        "type": "function",
        "function": {
            "name": entry.tool_name,
            "description": entry.description,
            "parameters": entry.input_schema or {"type": "object", "properties": {}},
        },
    }


def to_anthropic_schema(entry: ToolEntry) -> dict[str, Any]:
    """Generate Anthropic tool use definition for a tool.

    Format: {"name": ..., "description": ..., "input_schema": ...}

    Args:
        entry: ToolEntry describing the tool.

    Returns:
        Anthropic-compatible tool definition.
    """
    return {
        "name": entry.tool_name,
        "description": entry.description,
        "input_schema": entry.input_schema or {"type": "object", "properties": {}},
    }


def to_gemini_schema(entry: ToolEntry) -> dict[str, Any]:
    """Generate Google Gemini function declaration for a tool.

    Format: {"name": ..., "description": ..., "parameters": ...}

    Args:
        entry: ToolEntry describing the tool.

    Returns:
        Gemini-compatible function declaration.
    """
    # Gemini uses a slightly simplified parameter format
    params = entry.input_schema or {"type": "object", "properties": {}}
    return {
        "name": entry.tool_name,
        "description": entry.description,
        "parameters": params,
    }
