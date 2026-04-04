"""Use ToolsConnector with OpenAI function calling.

Full loop: generate tool schemas, send to OpenAI, execute the tool
call that comes back, and feed the result back into the conversation.

Prerequisites:
    pip install toolsconnector[github] openai
    export TC_GITHUB_CREDENTIALS='ghp_your-personal-access-token'
    export OPENAI_API_KEY='sk-your-key'
"""

import json
import os

from openai import OpenAI

from toolsconnector.serve import ToolKit

# -- Setup --

client = OpenAI()

# Create a read-only ToolKit for GitHub.
# include_actions accepts glob patterns to whitelist specific actions.
kit = ToolKit(
    connectors=["github"],
    credentials={"github": os.environ.get("TC_GITHUB_CREDENTIALS", "")},
    include_actions=["list_*", "get_*", "search_*"],  # read-only subset
)

# Generate OpenAI-compatible tool definitions.
# These match the `tools` parameter format for chat.completions.create.
tools = kit.to_openai_tools()
print(f"Registered {len(tools)} tools with OpenAI")

# -- Chat with tool use --

messages = [
    {"role": "user", "content": "List the 3 most recent repos for the 'anthropics' org"},
]

response = client.chat.completions.create(
    model="gpt-4",
    messages=messages,
    tools=tools,
)

# -- Process tool calls --

for choice in response.choices:
    message = choice.message

    if message.tool_calls:
        # The model wants to call one or more tools
        for call in message.tool_calls:
            print(f"\nCalling: {call.function.name}")
            print(f"Args: {call.function.arguments}")

            # Execute through ToolKit -- handles auth, retries, timeouts
            result = kit.execute(
                call.function.name,
                json.loads(call.function.arguments),
            )
            print(f"Result: {result[:200]}...")
    else:
        # The model responded with text (no tool call needed)
        print(f"Response: {message.content}")
