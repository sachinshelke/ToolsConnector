#!/bin/bash
# ToolsConnector CLI examples
#
# The `tc` command is installed automatically with the package.
# It provides quick access to connectors without writing Python.
#
# Prerequisites:
#   pip install toolsconnector[gmail,slack,github]
#   export TC_GMAIL_CREDENTIALS='your-token'

# List all registered connectors (currently 50+)
tc list

# Show all actions available for the Gmail connector
tc gmail actions

# Execute an action directly from the command line.
# Arguments are passed as --flag value pairs.
tc gmail list_emails --query "is:unread" --limit 5

# Export a connector's spec as JSON (useful for code generation)
tc gmail spec --format json

# Start an MCP server for Claude Desktop (blocks on stdio)
# tc serve mcp gmail slack --transport stdio

# Start a REST API server on port 8000
# tc serve rest gmail slack --port 8000
