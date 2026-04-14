# Airtable

> Flexible database-spreadsheet hybrid for teams

| | |
|---|---|
| **Company** | Airtable Inc. |
| **Category** | Database |
| **Protocol** | REST |
| **Website** | [airtable.com](https://airtable.com) |
| **API Docs** | [airtable.com](https://airtable.com/developers/web/api/introduction) |
| **Auth** | Personal Access Token, OAuth 2.0 |
| **Rate Limit** | 5 requests/second per base |
| **Pricing** | Free tier, Team from $20/seat/month |

---

## Overview

The Airtable API lets you create, read, update, and delete records in your Airtable bases. Manage tables, fields, views, and webhooks. Build data-driven apps, content calendars, and project trackers backed by Airtable's flexible schema.

## Use Cases

- Content calendar management
- CRM and lead tracking
- Project management
- Inventory management
- Survey and form data collection

## Installation

```bash
pip install "toolsconnector[airtable]"
```

Set your credentials:

```bash
export TC_AIRTABLE_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["airtable"], credentials={"airtable": "your-token"})

# List records from an Airtable table
result = kit.execute("airtable_list_records", {"base_id": "your-base_id", "table_name": "your-table_name", "fields": "your-fields", "filter_formula": "your-filter_formula"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["airtable"], credentials={"airtable": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["airtable"], credentials={"airtable": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### Personal Access Token

1. Create an account at [Airtable](https://airtable.com)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://airtable.com/create/tokens)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("airtable_list_records", {})
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

- Use batch operations (`batch_create`) for bulk operations instead of individual calls
- Rate limit is 5 requests/second per base — use pagination and caching to minimize API calls
- Actions marked as destructive (`create_comment`, `create_field`, `create_table`) cannot be undone — use with caution
- Use cursor-based pagination for large result sets — pass the `cursor` from previous responses

## Related Connectors

- [Firestore](../firestore/) — Document database
- [Mongodb](../mongodb/) — NoSQL database
- [Redis](../redis/) — Key-value store
- [Supabase](../supabase/) — Postgres as a service

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
