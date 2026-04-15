"""MCP server integration.

Creates and runs an MCP server from a ToolKit instance.
Tools are dynamically registered from the ToolKit's filtered tool list.
"""

from __future__ import annotations

import functools
import json
import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from toolsconnector.serve.toolkit import ToolKit

logger = logging.getLogger("toolsconnector.serve.mcp")


def _make_tool_handler(toolkit: "ToolKit", tool_name: str) -> Any:
    """Return an async handler whose signature is *only* **kwargs.

    Using a factory function (instead of a default-argument closure) prevents
    the captured ``tool_name`` from appearing as a positional parameter in
    ``inspect.signature()``.  FastMCP, OpenAI schema generators, and Pydantic
    all call ``inspect.signature()`` to build the tool input schema, so any
    non-``**kwargs`` parameter would be incorrectly surfaced as a user-facing
    input field.

    Args:
        toolkit: The ToolKit instance that owns the connector.
        tool_name: The fully-qualified tool name (``"{connector}_{action}"``).

    Returns:
        An async callable that accepts only ``**kwargs`` at call time.
    """
    async def _handler(**kwargs: Any) -> str:
        try:
            result = await toolkit.aexecute(tool_name, kwargs)
            return result if isinstance(result, str) else json.dumps(result, default=str)
        except Exception as e:
            # Log and re-raise — FastMCP converts the exception to an isError
            # MCP response automatically.
            logger.error(f"Tool {tool_name} failed: {e}")
            raise

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

    # Register each tool
    for entry_dict in tool_entries:
        tool_name = entry_dict["name"]
        description = entry_dict["description"]

        # Build the handler via a factory so 'tool_name' is never a parameter
        # visible to inspect.signature().  Only **kwargs is exposed, which is
        # intentionally omitted from schema generation by FastMCP/OpenAI.
        handler = _make_tool_handler(toolkit, tool_name)
        handler.__name__ = tool_name
        handler.__doc__ = description

        # Register with FastMCP using explicit name + description so the schema
        # is built from entry metadata, not from the handler's signature.
        server.tool(name=tool_name, description=description)(handler)

    logger.info(f"Starting MCP server (transport={transport})")

    # Run the server
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
