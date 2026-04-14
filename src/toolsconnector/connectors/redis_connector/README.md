# Redis (Upstash)

> Serverless Redis with HTTP API

| | |
|---|---|
| **Company** | Upstash Inc. |
| **Category** | Database |
| **Protocol** | REST |
| **Website** | [upstash.com](https://upstash.com) |
| **API Docs** | [upstash.com](https://upstash.com/docs/redis/overall/getstarted) |
| **Auth** | Bearer Token |
| **Rate Limit** | 1,000 requests/second |
| **Pricing** | Free tier (10K commands/day), Pay-as-you-go from $0.2/100K commands |

---

## Overview

The Upstash Redis REST API provides HTTP-based access to Redis data structures. Execute Redis commands over HTTP, manage keys, work with strings, lists, sets, hashes, and sorted sets without maintaining persistent connections.

## Use Cases

- Serverless caching
- Session management
- Rate limiting
- Real-time leaderboards
- Pub/sub messaging

## Installation

```bash
pip install "toolsconnector[redis]"
```

Set your credentials:

```bash
export TC_REDIS_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["redis"], credentials={"redis": "your-token"})

# Append a value to a Redis string key
result = kit.execute("redis_append", {"key": "my-key", "value": "my-value"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["redis"], credentials={"redis": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["redis"], credentials={"redis": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### Bearer Token

1. Create an account at [Redis (Upstash)](https://upstash.com)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://console.upstash.com/)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("redis_append", {})
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

- Rate limit is 1,000 requests/second — use pagination and caching to minimize API calls
- Actions marked as destructive (`delete`) cannot be undone — use with caution

## Related Connectors

- [Airtable](../airtable/) — Spreadsheet database
- [Firestore](../firestore/) — Document database
- [Mongodb](../mongodb/) — NoSQL database
- [Supabase](../supabase/) — Postgres as a service

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
