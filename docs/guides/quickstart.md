# Quickstart

Get from zero to a working tool call in under 5 minutes.

## 1. Install

```bash
pip install toolsconnector
```

Install only the connectors you need:

```bash
pip install "toolsconnector[gmail,slack]"
```

## 2. Set Credentials

Export your API tokens as environment variables. ToolsConnector follows the BYOK (Bring Your Own Key) model -- you provide the credentials, the library handles the protocol.

```bash
export TC_GMAIL_CREDENTIALS="ya29.your-google-access-token"
export TC_SLACK_CREDENTIALS="xoxb-your-slack-bot-token"
```

Or pass credentials directly in code (see step 3).

## 3. Create a ToolKit

The `ToolKit` is the single entry point for all operations. Initialize it with the connectors you want and their credentials.

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(
    ["gmail", "slack"],
    credentials={
        "gmail": "ya29.your-google-access-token",
        "slack": "xoxb-your-slack-bot-token",
    },
)
```

## 4. List Available Tools

Discover all registered actions across your configured connectors.

```python
tools = kit.list_tools()
for tool in tools:
    print(f"{tool.name}: {tool.description}")
```

Expected output:

```
gmail_list_emails: List emails matching a query
gmail_get_email: Get a single email by ID
gmail_send_email: Send an email
slack_send_message: Send a message to a Slack channel or thread
slack_list_channels: List channels in the workspace
...
```

## 5. Execute a Tool Call

Call any action by its fully qualified name (`{connector}_{action}`) and a parameter dict.

```python
# List unread emails
result = kit.execute("gmail_list_emails", {"query": "is:unread", "max_results": 5})
print(result)

# Send a Slack message
kit.execute("slack_send_message", {
    "channel": "#general",
    "text": "Deployed v2.1 successfully",
})
```

The async equivalent uses `aexecute`:

```python
result = await kit.aexecute("gmail_list_emails", {"query": "is:unread"})
```

## 6. Generate AI Function-Calling Schemas

Generate tool schemas for any AI provider from the same source of truth.

**OpenAI:**

```python
openai_tools = kit.to_openai_tools()
# Pass directly to client.chat.completions.create(tools=openai_tools)
```

**Anthropic:**

```python
anthropic_tools = kit.to_anthropic_tools()
# Pass directly to client.messages.create(tools=anthropic_tools)
```

**Gemini:**

```python
gemini_tools = kit.to_gemini_tools()
# Pass to google.generativeai as function_declarations
```

## 7. Start an MCP Server

Expose your configured connectors to Claude Desktop, Cursor, or any MCP client with a single call.

```python
kit.serve_mcp()  # Starts stdio transport, blocks until client disconnects
```

Or from the command line:

```bash
tc serve mcp gmail slack --transport stdio
```

See [MCP Server Guide](mcp-server.md) for Claude Desktop and Cursor configuration.

---

## Next Steps

- [MCP Server Guide](mcp-server.md) -- serve connectors to AI clients
- [AI Frameworks Guide](ai-frameworks.md) -- full integration examples for OpenAI, Anthropic, LangChain, CrewAI
- [Credentials Guide](credentials.md) -- advanced credential management
- [Adding a Connector](adding-connector.md) -- build your own connector
- [API Reference](../API.md) -- full class and method reference
