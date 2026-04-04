"""Start an MCP server for Claude Desktop / Cursor.

MCP (Model Context Protocol) lets AI assistants call your tools
over stdio or HTTP. This script starts a server that exposes
your connectors as MCP tools.

Prerequisites:
    pip install toolsconnector[mcp,gmail,slack]
    export TC_GMAIL_CREDENTIALS='your-token'
    export TC_SLACK_CREDENTIALS='your-token'

Then add to your Claude Desktop config (~/.claude/claude_desktop_config.json):
{
  "mcpServers": {
    "toolsconnector": {
      "command": "python",
      "args": ["examples/02_mcp_server.py"]
    }
  }
}
"""

from toolsconnector.serve import ToolKit

# Create a ToolKit with multiple connectors.
# exclude_dangerous=True filters out destructive actions (delete, send)
# so the AI can only read data -- never modify it without explicit config.
kit = ToolKit(
    connectors=["gmail", "slack"],
    exclude_dangerous=True,
)

# serve_mcp() blocks and runs the MCP server on stdio.
# Claude Desktop (or any MCP client) connects automatically.
# Supported transports: "stdio" (default), "http".
kit.serve_mcp(name="my-tools")
