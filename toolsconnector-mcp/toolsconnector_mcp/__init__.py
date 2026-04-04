"""ToolsConnector MCP — Enhanced Model Context Protocol server.

Extends the base ToolsConnector serve layer with:
- Smart tool selection (filter tools by relevance to a query)
- Multi-tenant MCP serving (per-user credentials)
- Schema optimization (reduce token usage in tool definitions)
- Tool capability discovery
"""

from toolsconnector_mcp.server import MCPServer
from toolsconnector_mcp.selection import SmartToolSelector

__all__ = ["MCPServer", "SmartToolSelector"]
