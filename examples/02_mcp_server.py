"""Start an MCP server for Claude Desktop / Cursor / agent runtimes.

MCP (Model Context Protocol) lets AI assistants call your tools.
This script starts a server that exposes connectors as MCP tools.

Three transports are supported:

    stdio              — JSON-RPC over stdin/stdout, one client per
                         process. Use when an MCP host (Claude Desktop,
                         Cursor) launches this script as a subprocess.
                         This is the default.

    sse                — Server-Sent Events over HTTP. Long-lived
                         daemon, many concurrent clients. Being
                         deprecated upstream in favor of streamable-http.

    streamable-http    — Current MCP-spec HTTP transport. Long-lived
                         daemon, many concurrent clients. Recommended
                         for production deployments where one
                         ToolsConnector daemon serves many agents.

Prerequisites:
    pip install "toolsconnector[mcp,gmail,slack]"
    export TC_GMAIL_CREDENTIALS='your-token'
    export TC_SLACK_CREDENTIALS='your-token'

Stdio (Claude Desktop config — ~/.claude/claude_desktop_config.json):
{
  "mcpServers": {
    "toolsconnector": {
      "command": "python",
      "args": ["examples/02_mcp_server.py"]
    }
  }
}

Daemon (one process, many agents):
    python examples/02_mcp_server.py --daemon
"""

import sys

from toolsconnector.serve import ToolKit

# Create a ToolKit with multiple connectors.
# exclude_dangerous=True filters out destructive actions (delete, send)
# so the AI can only read data -- never modify it without explicit config.
kit = ToolKit(
    connectors=["gmail", "slack"],
    exclude_dangerous=True,
)

# Pass --daemon on the command line to switch to long-lived HTTP mode.
if "--daemon" in sys.argv:
    # Multiple concurrent agents can connect to localhost:9000 and share
    # this one running process. Per-tool circuit breakers + timeout
    # budgets apply across all clients fairly.
    kit.serve_mcp(name="my-tools", transport="streamable-http", port=9000)
else:
    # serve_mcp() blocks and runs the MCP server on stdio.
    # Claude Desktop (or any MCP client) connects automatically.
    kit.serve_mcp(name="my-tools")
