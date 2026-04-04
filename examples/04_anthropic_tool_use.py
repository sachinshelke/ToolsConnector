"""Use ToolsConnector with Anthropic Claude tool use.

Same pattern as the OpenAI example but using the Anthropic SDK.
ToolKit generates the correct schema format for each provider.

Prerequisites:
    pip install toolsconnector[slack] anthropic
    export TC_SLACK_CREDENTIALS='xoxb-your-bot-token'
    export ANTHROPIC_API_KEY='sk-ant-your-key'
"""

import os

from anthropic import Anthropic

from toolsconnector.serve import ToolKit

# -- Setup --

client = Anthropic()

# Create a read-only ToolKit for Slack.
kit = ToolKit(
    connectors=["slack"],
    credentials={"slack": os.environ.get("TC_SLACK_CREDENTIALS", "")},
    include_actions=["list_*", "get_*"],  # read-only subset
)

# Generate Anthropic-compatible tool definitions.
# These match the `tools` parameter format for messages.create.
tools = kit.to_anthropic_tools()
print(f"Registered {len(tools)} tools with Claude")

# -- Chat with tool use --

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    tools=tools,
    messages=[{"role": "user", "content": "List the Slack channels"}],
)

# -- Process the response --

for block in response.content:
    if block.type == "tool_use":
        # Claude wants to call a tool
        print(f"\nCalling: {block.name}")
        print(f"Args: {block.input}")

        # Execute through ToolKit
        result = kit.execute(block.name, block.input)
        print(f"Result: {result[:200]}...")
    elif block.type == "text":
        # Claude responded with text
        print(f"Claude: {block.text}")
