# MCP Server Guide

How to expose ToolsConnector actions to Claude Desktop, Cursor, and other MCP clients.

## What is MCP?

The Model Context Protocol (MCP) is an open standard for connecting AI models to external tools and data sources. An MCP server advertises a set of tools -- each with a name, description, and JSON Schema for inputs -- and the AI client calls them as needed during a conversation.

ToolsConnector can serve any combination of its 53+ connectors as an MCP server with a single line of code or CLI command.

## Install

The MCP transport layer is an optional dependency:

```bash
pip install "toolsconnector[mcp]"
```

Or combine with specific connectors:

```bash
pip install "toolsconnector[gmail,slack,github,mcp]"
```

## Python Usage

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(
    ["gmail", "slack", "github"],
    credentials={
        "gmail": "ya29.token",
        "slack": "xoxb-token",
        "github": "ghp_token",
    },
)

# Start the MCP server (stdio transport, blocks until client disconnects)
kit.serve_mcp()
```

For SSE or streamable HTTP transports:

```python
kit.serve_mcp(transport="sse", port=8080)
kit.serve_mcp(transport="streamable-http", port=8080)
```

## CLI Usage

```bash
tc serve mcp gmail slack github --transport stdio
```

Credentials are read from environment variables (`TC_GMAIL_CREDENTIALS`, `TC_SLACK_CREDENTIALS`, etc.) when using the CLI.

Transport options:

```bash
tc serve mcp gmail --transport stdio            # Default, for desktop apps
tc serve mcp gmail --transport sse --port 8080  # For networked clients
tc serve mcp gmail --transport streamable-http --port 8080
```

## Claude Desktop Configuration

Add to your Claude Desktop configuration file:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "toolsconnector": {
      "command": "tc",
      "args": ["serve", "mcp", "gmail", "slack", "github", "--transport", "stdio"],
      "env": {
        "TC_GMAIL_CREDENTIALS": "ya29.your-token",
        "TC_SLACK_CREDENTIALS": "xoxb-your-token",
        "TC_GITHUB_CREDENTIALS": "ghp_your-token"
      }
    }
  }
}
```

Restart Claude Desktop after editing the configuration.

## Cursor IDE Configuration

Add to `.cursor/mcp.json` in your project root:

```json
{
  "mcpServers": {
    "toolsconnector": {
      "command": "tc",
      "args": ["serve", "mcp", "github", "jira", "--transport", "stdio"],
      "env": {
        "TC_GITHUB_CREDENTIALS": "ghp_your-token",
        "TC_JIRA_CREDENTIALS": "your-jira-api-token"
      }
    }
  }
}
```

## Transport Options

| Transport | Use Case | Protocol |
|-----------|----------|----------|
| `stdio` | Desktop apps (Claude Desktop, Cursor) | stdin/stdout JSON-RPC |
| `sse` | Networked clients, multi-user | HTTP + Server-Sent Events |
| `streamable-http` | Modern MCP clients | HTTP streaming |

Use `stdio` for local desktop integrations. Use `sse` or `streamable-http` when the MCP server runs on a different machine or serves multiple clients.

## Filtering Dangerous Actions

Actions marked as `dangerous=True` (send, delete, create operations) can be excluded from the MCP server to prevent unintended side effects:

```python
kit.serve_mcp(exclude_dangerous=True)
```

Or include only specific actions:

```python
kit.serve_mcp(include_actions=["gmail_list_emails", "gmail_get_email"])
```

## Troubleshooting

**Server does not appear in Claude Desktop:**
Verify the `command` path is correct. Run `which tc` to find the full path and use the absolute path in the config.

**Authentication errors:**
Check that environment variables are set correctly. Run `tc gmail actions` to verify the connector can initialize.

**Connection refused (SSE/HTTP):**
Ensure the port is not in use. Check firewall rules if the client is on a different machine.

**Timeout on large responses:**
Increase the timeout budget: `kit.serve_mcp(timeout=60)`.
