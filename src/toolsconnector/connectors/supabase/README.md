# Supabase

> Open-source Firebase alternative with Postgres

| | |
|---|---|
| **Company** | Supabase Inc. |
| **Category** | Database |
| **Protocol** | REST |
| **Website** | [supabase.com](https://supabase.com) |
| **API Docs** | [supabase.com](https://supabase.com/docs/guides/api) |
| **Auth** | API Key (anon/service_role) |
| **Rate Limit** | Varies by plan |
| **Pricing** | Free tier, Pro from $25/month |

---

## Overview

The Supabase API provides RESTful access to your Postgres database, authentication, and storage. Query tables, manage rows, handle file uploads, and build full-stack applications with Supabase's auto-generated API.

## Use Cases

- Database CRUD operations
- User authentication
- File storage
- Real-time subscriptions
- Serverless backends

## Installation

```bash
pip install toolsconnector[supabase]
```

Set your credentials:

```bash
export TC_SUPABASE_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["supabase"], credentials={"supabase": "your-token"})

# Get a single record from a Supabase table by ID
result = kit.execute("supabase_get_record", {"table": "your-table", "id": "your-id"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["supabase"], credentials={"supabase": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["supabase"], credentials={"supabase": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### API Key (anon/service_role)

1. Create an account at [Supabase](https://supabase.com)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://supabase.com/dashboard/)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("supabase_get_record", {})
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

- Rate limit is Varies by plan — use pagination and caching to minimize API calls
- Actions marked as destructive (`auth_sign_up`, `delete_record`, `insert_many`) cannot be undone — use with caution

## Related Connectors

- [Airtable](../airtable/) — Spreadsheet database
- [Firestore](../firestore/) — Document database
- [Mongodb](../mongodb/) — NoSQL database
- [Redis](../redis/) — Key-value store

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
