"""ToolsConnector Serve Layer.

The serve layer turns connectors into tools for any AI framework.
Everything flows through :class:`ToolKit` — configure once, use everywhere.

Quick start::

    from toolsconnector.serve import ToolKit

    kit = ToolKit(["gmail", "slack"], credentials={...})

    # MCP server (Claude Desktop, Cursor)
    kit.serve_mcp()

    # OpenAI function calling
    tools = kit.to_openai_tools()

    # Execute tool calls
    result = await kit.aexecute("gmail_list_emails", {"query": "is:unread"})
"""

from toolsconnector.serve._discovery import get_connector_class, list_connectors
from toolsconnector.serve.toolkit import ToolKit, ToolKitFactory

__all__ = [
    "ToolKit",
    "ToolKitFactory",
    "list_connectors",
    "get_connector_class",
]
