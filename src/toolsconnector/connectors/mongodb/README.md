# MongoDB Atlas

> Cloud-hosted NoSQL document database

| | |
|---|---|
| **Company** | MongoDB Inc. |
| **Category** | Database |
| **Protocol** | REST |
| **Website** | [www.mongodb.com/atlas](https://www.mongodb.com/atlas) |
| **API Docs** | [www.mongodb.com](https://www.mongodb.com/docs/atlas/api/) |
| **Auth** | API Key |
| **Rate Limit** | 300 requests/minute (Data API) |
| **Pricing** | Free tier (M0), Dedicated from $57/month |

---

## Overview

The MongoDB Atlas Data API provides RESTful access to your MongoDB Atlas clusters. Query documents, run aggregation pipelines, insert and update data, and manage collections without direct driver connections.

## Use Cases

- Document CRUD operations
- Aggregation pipelines
- Serverless data access
- Edge data queries
- Cross-platform data sync

## Installation

```bash
pip install toolsconnector[mongodb]
```

Set your credentials:

```bash
export TC_MONGODB_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["mongodb"], credentials={"mongodb": "your-token"})

# List databases available in the MongoDB cluster
result = kit.execute("mongodb_list_databases", {})
print(result)
```

### MCP Server

```python
kit = ToolKit(["mongodb"], credentials={"mongodb": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["mongodb"], credentials={"mongodb": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### API Key

1. Create an account at [MongoDB Atlas](https://www.mongodb.com/atlas)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://cloud.mongodb.com/)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("mongodb_list_databases", {})
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

- Rate limit is 300 requests/minute (Data API) — use pagination and caching to minimize API calls
- Actions marked as destructive (`delete_many`, `delete_one`, `drop_collection`) cannot be undone — use with caution

## Related Connectors

- [Airtable](../airtable/) — Spreadsheet database
- [Firestore](../firestore/) — Document database
- [Redis](../redis/) — Key-value store
- [Supabase](../supabase/) — Postgres as a service

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
