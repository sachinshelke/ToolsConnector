"""MCP server integration.

Creates and runs an MCP server from a ToolKit instance.
Tools are dynamically registered from the ToolKit's filtered tool list.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from toolsconnector.serve.toolkit import ToolKit

logger = logging.getLogger("toolsconnector.serve.mcp")


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
        transport: Transport protocol ("stdio", "sse", "streamable-http").
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
            "Install with: pip install toolsconnector[mcp]"
        )

    server = FastMCP(name)
    tool_entries = toolkit.list_tools()

    logger.info(f"Registering {len(tool_entries)} tools with MCP server '{name}'")

    # Register each tool
    for entry_dict in tool_entries:
        tool_name = entry_dict["name"]
        description = entry_dict["description"]
        input_schema = entry_dict.get("input_schema", {})

        # Build the handler function
        # Use default args to capture loop variable
        async def _handler(
            _tool_name: str = tool_name,
            **kwargs: Any,
        ) -> str:
            try:
                result = await toolkit.aexecute(_tool_name, kwargs)
                return result if isinstance(result, str) else json.dumps(result, default=str)
            except Exception as e:
                # Log and re-raise — FastMCP handles exception -> isError response
                logger.error(f"Tool {_tool_name} failed: {e}")
                raise

        # Set function metadata for FastMCP
        _handler.__name__ = tool_name
        _handler.__doc__ = description

        # Register with FastMCP
        # FastMCP's @tool() accepts the function and uses its name/doc
        server.tool(name=tool_name, description=description)(_handler)

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
