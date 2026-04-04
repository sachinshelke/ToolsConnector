"""Multi-connector ToolKit with safety filtering.

Shows how to configure multiple connectors with different
credentials and generate schemas for every major AI framework
from a single ToolKit instance.
"""

import os

from toolsconnector.serve import ToolKit

# Create a ToolKit with five connectors at once.
# Each connector gets its own credentials, but they share
# the same filtering rules and timeout budget.
kit = ToolKit(
    connectors=["gmail", "slack", "github", "notion", "jira"],
    credentials={
        "gmail": os.environ.get("TC_GMAIL_CREDENTIALS", ""),
        "slack": os.environ.get("TC_SLACK_CREDENTIALS", ""),
        "github": os.environ.get("TC_GITHUB_CREDENTIALS", ""),
        "notion": os.environ.get("TC_NOTION_CREDENTIALS", ""),
        "jira": os.environ.get("TC_JIRA_CREDENTIALS", ""),
    },
    exclude_dangerous=True,                        # no delete/send actions
    include_actions=["list_*", "get_*", "search_*"],  # read-only subset
)

# Inspect what was loaded
print(f"ToolKit: {len(kit.list_tools())} safe, read-only tools")
print(f"Connectors: {kit.connector_names}")
print()

# Generate schemas for every major AI framework from the same ToolKit.
# The tool definitions differ only in envelope format -- the action
# names, descriptions, and input schemas are identical.
openai_tools = kit.to_openai_tools()
anthropic_tools = kit.to_anthropic_tools()
gemini_tools = kit.to_gemini_tools()

print(f"OpenAI schemas:    {len(openai_tools)} tools")
print(f"Anthropic schemas: {len(anthropic_tools)} tools")
print(f"Gemini schemas:    {len(gemini_tools)} tools")
