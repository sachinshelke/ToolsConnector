"""Enhanced MCP server with multi-tenant and smart selection.

Builds on top of ToolKit to provide production-grade MCP serving:
- Per-tenant credential isolation
- Dynamic tool filtering based on context
- Optimized schema descriptions to save tokens
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger("toolsconnector.mcp")


def _make_tool_handler(toolkit: Any, tool_name: str) -> Any:
    """Return an async handler whose public signature is *only* ``**kwargs``.

    Using a factory function instead of a default-argument closure ensures that
    the captured ``tool_name`` variable never surfaces as a positional parameter
    when ``inspect.signature()`` is called.  FastMCP, OpenAI schema generators,
    Pydantic, and LangChain all use ``inspect.signature()`` to derive the tool's
    input schema, so a naked positional default would incorrectly appear as a
    required/optional user field.

    Args:
        toolkit: The ToolKit that owns the connector.
        tool_name: Fully-qualified tool name (``"{connector}_{action}"``).

    Returns:
        An async callable ``(**kwargs: Any) -> str``.
    """
    async def _handler(**kwargs: Any) -> str:
        try:
            result = await toolkit.aexecute(tool_name, kwargs)
            return (
                result
                if isinstance(result, str)
                else json.dumps(result, default=str)
            )
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}")
            raise

    return _handler


class MCPServer:
    """Production-grade MCP server for ToolsConnector.

    Extends the basic ``ToolKit.serve_mcp()`` with:
    - Multi-tenant credential management
    - Smart tool selection (filter by relevance)
    - Schema optimization (shorter descriptions for token savings)

    Usage::

        from toolsconnector_mcp import MCPServer

        server = MCPServer(
            connectors=["gmail", "slack", "github"],
            default_credentials={"gmail": "...", "slack": "..."},
        )
        server.run()  # starts stdio MCP server
    """

    def __init__(
        self,
        connectors: list[str],
        *,
        default_credentials: Optional[dict[str, str]] = None,
        include_actions: Optional[list[str]] = None,
        exclude_actions: Optional[list[str]] = None,
        exclude_dangerous: bool = False,
        name: str = "toolsconnector",
        optimize_schemas: bool = True,
    ) -> None:
        """Initialize the MCP server.

        Args:
            connectors: List of connector names to serve.
            default_credentials: Default credentials for connectors.
            include_actions: Glob patterns for actions to include.
            exclude_actions: Glob patterns for actions to exclude.
            exclude_dangerous: Whether to exclude dangerous actions.
            name: Server name shown to MCP clients.
            optimize_schemas: Whether to optimize tool descriptions.
        """
        from toolsconnector.serve import ToolKit

        self._name = name
        self._optimize = optimize_schemas
        self._toolkit = ToolKit(
            connectors,
            credentials=default_credentials,
            include_actions=include_actions,
            exclude_actions=exclude_actions,
            exclude_dangerous=exclude_dangerous,
        )

    def run(
        self,
        *,
        transport: str = "stdio",
        port: int = 3000,
    ) -> None:
        """Start the MCP server.

        Args:
            transport: Transport protocol (stdio, sse, streamable-http).
            port: Port for HTTP transports.
        """
        try:
            from mcp.server.fastmcp import FastMCP
        except ImportError:
            raise ImportError(
                "MCP server requires the 'mcp' package. "
                "Install with: pip install toolsconnector-mcp"
            )

        server = FastMCP(self._name)
        tools = self._toolkit.list_tools()

        logger.info(
            f"Registering {len(tools)} tools with MCP server "
            f"'{self._name}'"
        )

        for entry in tools:
            tool_name = entry["name"]
            description = entry["description"]

            if self._optimize:
                description = self._optimize_description(description)

            # Build the handler via a module-level factory so 'tool_name' is
            # never a parameter visible to inspect.signature().
            handler = _make_tool_handler(self._toolkit, tool_name)
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
            raise ValueError(f"Unknown transport '{transport}'")

    def _optimize_description(self, description: str) -> str:
        """Shorten tool descriptions to save LLM context tokens.

        Keeps the first sentence and strips verbose details.

        Args:
            description: Full tool description.

        Returns:
            Optimized (shorter) description.
        """
        if len(description) <= 100:
            return description

        # Keep first sentence
        for sep in (". ", ".\n", ".\t"):
            idx = description.find(sep)
            if idx != -1 and idx < 150:
                return description[: idx + 1]

        # Truncate at 120 chars
        return description[:117] + "..."

    @property
    def tool_count(self) -> int:
        """Number of registered tools."""
        return len(self._toolkit.list_tools())

    @property
    def connector_names(self) -> list[str]:
        """Names of configured connectors."""
        return sorted(self._toolkit._connector_classes.keys())
