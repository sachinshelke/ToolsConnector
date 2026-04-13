# Anthropic

> Claude models for safe, capable AI

| | |
|---|---|
| **Company** | Anthropic |
| **Category** | Ai Ml |
| **Protocol** | REST |
| **Website** | [anthropic.com](https://anthropic.com) |
| **API Docs** | [docs.anthropic.com](https://docs.anthropic.com/en/api) |
| **Auth** | API Key |
| **Rate Limit** | Varies by model and tier |
| **Pricing** | Pay-per-token (varies by model) |

---

## Overview

The Anthropic API provides access to Claude models for text generation, analysis, and tool use. Build AI assistants, automate reasoning tasks, and integrate Claude's capabilities into your applications. Supports streaming, batching, and multi-turn conversations.

## Use Cases

- AI assistants and chatbots
- Document analysis
- Code generation
- Research automation
- Content creation

## Installation

```bash
pip install toolsconnector[anthropic]
```

Set your credentials:

```bash
export TC_ANTHROPIC_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["anthropic"], credentials={"anthropic": "your-token"})

# List uploaded files
result = kit.execute("anthropic_list_files", {"limit": 20})
print(result)
```

### MCP Server

```python
kit = ToolKit(["anthropic"], credentials={"anthropic": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["anthropic"], credentials={"anthropic": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### API Key

1. Console
2. Settings
3. API Keys

[Get credentials &rarr;](https://console.anthropic.com/settings/keys)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("anthropic_list_files", {})
except RateLimitError as e:
    print(f"Rate limited. Retry in {e.retry_after_seconds}s")
except AuthError as e:
    print(f"Auth failed: {e.suggestion}")
```

## Actions

<!-- ACTIONS_START -->
<!-- This section is auto-generated from the connector spec. Do not edit manually. -->
<!-- ACTIONS_END -->

## Tips

- Use batch operations (`cancel_batch`, `create_batch`, `delete_message_batch`) for bulk operations instead of individual calls
- Rate limit is Varies by model and tier — use pagination and caching to minimize API calls
- Actions marked as destructive (`create_batch`, `delete_file`, `delete_message_batch`) cannot be undone — use with caution

## Related Connectors

- [Openai](../openai/) — GPT models
- [Pinecone](../pinecone/) — Vector database

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
