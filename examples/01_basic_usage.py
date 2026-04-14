"""Basic ToolsConnector usage -- 5 minutes to first API call.

This is the simplest possible example: create a ToolKit with one
connector, list the available tools, and execute an action.

Prerequisites:
    pip install "toolsconnector[gmail]"
    export TC_GMAIL_CREDENTIALS='your-oauth-token'

The credential format depends on the connector. Gmail expects an
OAuth2 access token (or a service-account JSON blob). See the
connector docs for details.
"""

import os

from toolsconnector.serve import ToolKit

# 1. Create a ToolKit with one connector.
#    ToolKit accepts connector names as strings -- it resolves them
#    to classes automatically via entry-point discovery.
kit = ToolKit(
    connectors=["gmail"],
    credentials={"gmail": os.environ.get("TC_GMAIL_CREDENTIALS", "")},
)

# 2. See what tools are available.
#    Each tool has a name, description, and input JSON schema.
tools = kit.list_tools()
print(f"Available tools ({len(tools)}):")
for tool in tools:
    print(f"  {tool['name']}: {tool['description']}")

# 3. Execute a tool call by name.
#    The first argument is the namespaced tool name ("{connector}_{action}").
#    The second argument is a dict matching the tool's input schema.
result = kit.execute("gmail_list_emails", {
    "query": "is:unread",
    "limit": 5,
})
print(f"\nResult:\n{result}")
