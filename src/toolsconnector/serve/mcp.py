"""MCP server integration.

Creates and runs an MCP server from a ToolKit instance.
Tools are dynamically registered from the ToolKit's filtered tool list.
"""

from __future__ import annotations

import inspect
import json
import logging
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from toolsconnector.serve.toolkit import ToolKit

logger = logging.getLogger("toolsconnector.serve.mcp")


def _json_type_to_python(param_schema: dict[str, Any], required: bool) -> Any:
    """Map a JSON Schema property definition to a Python type annotation.

    Args:
        param_schema: JSON Schema dict for a single property.
        required: Whether the parameter is required by the tool.

    Returns:
        A Python type suitable for use as an ``inspect.Parameter`` annotation.
    """
    json_type = param_schema.get("type", "string")
    type_map: dict[str, Any] = {
        "integer": int,
        "number": float,
        "boolean": bool,
        "string": str,
        "array": list,
        "object": dict,
    }
    py_type = type_map.get(json_type, Any)
    return py_type if required else Optional[py_type]  # type: ignore[return-value]


def _make_tool_handler(
    toolkit: "ToolKit",
    tool_name: str,
    input_schema: dict[str, Any],
) -> Any:
    """Return an async handler whose ``__signature__`` matches the tool's JSON Schema.

    FastMCP (and every other ``inspect.signature``-based schema generator)
    derives the tool's MCP input schema from the handler's parameter list.
    If the signature is ``(**kwargs: Any)`` FastMCP creates a single opaque
    ``kwargs`` parameter of type ``object`` and routes the LLM's arguments as
    ``_handler(kwargs={...})`` — wrapping the real args in a nested dict.

    By replacing ``__signature__`` with one built from the tool's actual JSON
    Schema properties, each tool's handler has the correct named parameters
    (e.g. ``q``, ``maxResults``).  FastMCP then:

    1. Generates the right per-parameter schema for LLM clients.
    2. Calls the handler as ``_handler(q="...", maxResults=50)``.
    3. ``kwargs`` inside the handler is ``{"q": "...", "maxResults": 50}``.
    4. ``aexecute(tool_name, kwargs)`` receives the correct ``arguments`` dict.
    5. ``method(**arguments)`` unpacks correctly into the connector action.

    Args:
        toolkit: The ToolKit instance that owns the connector.
        tool_name: Fully-qualified tool name (``"{connector}_{action}"``).
        input_schema: JSON Schema dict for the tool's input (from ToolEntry).

    Returns:
        An async callable with a proper ``__signature__`` for schema generation.
    """
    properties: dict[str, Any] = input_schema.get("properties", {})
    required_set: set[str] = set(input_schema.get("required", []))

    params: list[inspect.Parameter] = []
    for param_name, param_schema in properties.items():
        is_required = param_name in required_set
        params.append(
            inspect.Parameter(
                param_name,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=inspect.Parameter.empty if is_required else None,
                annotation=_json_type_to_python(param_schema, is_required),
            )
        )

    async def _handler(**kwargs: Any) -> str:
        try:
            result = await toolkit.aexecute(tool_name, kwargs)
            return result if isinstance(result, str) else json.dumps(result, default=str)
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}")
            raise

    # Replace the signature so FastMCP sees real parameter names, not **kwargs.
    _handler.__signature__ = inspect.Signature(params, return_annotation=str)
    return _handler


def create_and_run_mcp_server(
    toolkit: ToolKit,
    *,
    transport: str = "stdio",
    name: str = "toolsconnector",
    port: int = 3000,
) -> None:
    """Create and run an MCP server from a ToolKit.

    Dynamically registers all tools from the ToolKit's filtered list
    with a FastMCP server instance, then starts the server using the
    specified transport.

    Args:
        toolkit: Configured ToolKit instance.
        transport: Transport protocol (\"stdio\", \"sse\", \"streamable-http\").
        name: Server name shown to MCP clients.
        port: Port for HTTP transports.

    Raises:
        ImportError: If the ``mcp`` package is not installed.
        ValueError: If an unknown transport is specified.
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        raise ImportError(
            "MCP server requires the 'mcp' package. "
            'Install with: pip install "toolsconnector[mcp]"'
        )

    server = FastMCP(name)
    tool_entries = toolkit.list_tools()

    logger.info(f"Registering {len(tool_entries)} tools with MCP server '{name}'")

    for entry_dict in tool_entries:
        tool_name = entry_dict["name"]
        description = entry_dict["description"]
        input_schema = entry_dict.get("input_schema", {})

        handler = _make_tool_handler(toolkit, tool_name, input_schema)
        handler.__name__ = tool_name
        handler.__doc__ = description

        server.tool(name=tool_name, description=description)(handler)

    logger.info(f"Starting MCP server (transport={transport})")

    if transport == "stdio":
        server.run(transport="stdio")
    elif transport == "sse":
        server.run(transport="sse", port=port)
    elif transport == "streamable-http":
        server.run(transport="streamable-http", port=port)
    else:
        raise ValueError(
            f"Unknown transport '{transport}'. "
            f"Supported: 'stdio', 'sse', 'streamable-http'"
        )
