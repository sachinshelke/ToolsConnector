# Firebase Firestore

> Serverless NoSQL document database

| | |
|---|---|
| **Company** | Google (Firebase) |
| **Category** | Database |
| **Protocol** | REST |
| **Website** | [firebase.google.com/products/firestore](https://firebase.google.com/products/firestore) |
| **API Docs** | [firebase.google.com](https://firebase.google.com/docs/firestore/reference/rest) |
| **Auth** | Bearer Token (Firebase Auth), Service Account |
| **Rate Limit** | Varies by plan |
| **Pricing** | Free tier (Spark), Pay-as-you-go (Blaze) |

---

## Overview

The Firestore REST API provides access to documents and collections in your Firebase Firestore database. Query data with filters and ordering, perform batch operations, manage indexes, and build real-time applications.

## Use Cases

- Document storage and retrieval
- Real-time data sync
- Serverless backend
- Mobile app data layer
- IoT data collection

## Installation

```bash
pip install "toolsconnector[firestore]"
```

Set your credentials:

```bash
export TC_FIRESTORE_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["firestore"], credentials={"firestore": "your-token"})

# Get a Firestore document by ID
result = kit.execute("firestore_get_document", {"project": "my-project", "collection": "my-collection", "document_id": "doc-123"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["firestore"], credentials={"firestore": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["firestore"], credentials={"firestore": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### Bearer Token (Firebase Auth)

1. Create an account at [Firebase Firestore](https://firebase.google.com/products/firestore)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://console.firebase.google.com/)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("firestore_get_document", {})
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

- Use batch operations (`batch_get`, `batch_write`) for bulk operations instead of individual calls
- Rate limit is Varies by plan — use pagination and caching to minimize API calls
- Actions marked as destructive (`create_collection_group_index`, `delete_document`, `delete_index`) cannot be undone — use with caution

## Related Connectors

- [Airtable](../airtable/) — Spreadsheet database
- [Mongodb](../mongodb/) — NoSQL database
- [Redis](../redis/) — Key-value store
- [Supabase](../supabase/) — Postgres as a service

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
