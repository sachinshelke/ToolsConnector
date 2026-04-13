# RabbitMQ

> Open-source message broker and queue management

| | |
|---|---|
| **Company** | VMware (Broadcom) |
| **Category** | Message Queue |
| **Protocol** | REST |
| **Website** | [rabbitmq.com](https://rabbitmq.com) |
| **API Docs** | [rawcdn.githack.com](https://rawcdn.githack.com/rabbitmq/rabbitmq-server/v4.1.1/deps/rabbitmq_management/priv/www/api/index.html) |
| **Auth** | Basic Auth |
| **Rate Limit** | No hard limit (management API) |
| **Pricing** | Free (open-source), CloudAMQP from $0/month |

---

## Overview

The RabbitMQ Management HTTP API provides access to exchanges, queues, bindings, connections, and channels. Monitor broker health, manage queue configurations, publish and consume messages, and build reliable messaging workflows.

## Use Cases

- Message queue management
- Broker monitoring
- Queue configuration
- Exchange and binding setup
- Dead letter handling

## Installation

```bash
pip install toolsconnector[rabbitmq]
```

Set your credentials:

```bash
export TC_RABBITMQ_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["rabbitmq"], credentials={"rabbitmq": "your-token"})

# List active channels in the broker
result = kit.execute("rabbitmq_list_channels", {})
print(result)
```

### MCP Server

```python
kit = ToolKit(["rabbitmq"], credentials={"rabbitmq": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["rabbitmq"], credentials={"rabbitmq": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### Basic Auth

1. Create an account at [RabbitMQ](https://rabbitmq.com)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://rabbitmq.com/docs/management)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("rabbitmq_list_channels", {})
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

- Rate limit is No hard limit (management API) — use pagination and caching to minimize API calls
- Actions marked as destructive (`create_binding`, `create_exchange`, `create_queue`) cannot be undone — use with caution
- This connector has 21 actions — use `ToolKit(include_actions=[...])` to expose only what your agent needs

## Related Connectors

- [Sqs](../sqs/) — AWS queuing

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
