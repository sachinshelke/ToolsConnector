# Notion

> All-in-one workspace for notes, docs, and databases

| | |
|---|---|
| **Company** | Notion Labs Inc. |
| **Category** | Knowledge |
| **Protocol** | REST |
| **Website** | [notion.so](https://notion.so) |
| **API Docs** | [developers.notion.com](https://developers.notion.com/reference) |
| **Auth** | Bearer Token (Integration), OAuth 2.0 |
| **Rate Limit** | 3 requests/second average |
| **Pricing** | Free for personal, Plus from $10/user/month |

---

## Overview

The Notion API provides access to pages, databases, blocks, and users. Query and update databases, create and modify pages, manage content blocks, and build integrations that sync data with your Notion workspace.

## Use Cases

- Knowledge base management
- Content publishing
- Project tracking
- CRM in Notion databases
- Documentation automation

## Installation

```bash
pip install toolsconnector[notion]
```

Set your credentials:

```bash
export TC_NOTION_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["notion"], credentials={"notion": "your-token"})

# List all users in the workspace
result = kit.execute("notion_list_users", {})
print(result)
```

### MCP Server

```python
kit = ToolKit(["notion"], credentials={"notion": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["notion"], credentials={"notion": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### Bearer Token (Integration)

1. Settings
2. My Integrations
3. New Integration

[Get credentials &rarr;](https://www.notion.so/my-integrations)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("notion_list_users", {})
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

- Use `search` for filtered queries and `list_comments` for paginated browsing
- Rate limit is 3 requests/second average — use pagination and caching to minimize API calls
- Actions marked as destructive (`add_comment`, `append_block_children`, `archive_page`) cannot be undone — use with caution
- Use cursor-based pagination for large result sets — pass the `cursor` from previous responses

## Related Connectors

- [Confluence](../confluence/) — Team wiki

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
