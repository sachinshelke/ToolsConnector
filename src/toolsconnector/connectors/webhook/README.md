# Webhook

> Send and manage HTTP webhooks to any endpoint

| | |
|---|---|
| **Company** | ToolsConnector |
| **Category** | Custom |
| **Protocol** | REST |
| **Website** | [github.com/sachinshelke/ToolsConnector](https://github.com/sachinshelke/ToolsConnector) |
| **API Docs** | [github.com](https://github.com/sachinshelke/ToolsConnector) |
| **Auth** | Bearer Token, API Key, Custom Headers |
| **Rate Limit** | N/A (depends on target) |
| **Pricing** | Free (built-in connector) |

---

## Overview

The Webhook connector lets you send HTTP requests to any URL endpoint. Fire webhooks, manage retry logic, track delivery status, and build event-driven integrations with external services that accept webhooks.

## Use Cases

- Event notifications
- Service integration
- Custom API calls
- Webhook delivery with retry
- Cross-service triggers

## Installation

```bash
pip install "toolsconnector[webhook]"
```

Set your credentials:

```bash
export TC_WEBHOOK_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["webhook"], credentials={"webhook": "your-token"})

# Check if an endpoint is reachable
result = kit.execute("webhook_check_endpoint", {"url": "https://example.com"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["webhook"], credentials={"webhook": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["webhook"], credentials={"webhook": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### Bearer Token

1. Create an account at [Webhook](https://github.com/sachinshelke/ToolsConnector)
2. Navigate to API settings or developer console
3. Generate an API key or access token

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("webhook_check_endpoint", {})
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

- Use batch operations (`send_batch`) for bulk operations instead of individual calls
- Rate limit is N/A (depends on target) — use pagination and caching to minimize API calls
- Actions marked as destructive (`send_batch`, `send_form`, `send_graphql`) cannot be undone — use with caution

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
