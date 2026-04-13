# Google Docs

> Create and edit documents programmatically

| | |
|---|---|
| **Company** | Google |
| **Category** | Productivity |
| **Protocol** | REST |
| **Website** | [docs.google.com](https://docs.google.com) |
| **API Docs** | [developers.google.com](https://developers.google.com/docs/api/reference/rest) |
| **Auth** | OAuth 2.0, Service Account |
| **Rate Limit** | 300 requests/minute per project |
| **Pricing** | Free with Google account |

---

## Overview

The Google Docs API lets you create and modify Google Docs programmatically. Insert text, apply formatting, and extract content. Use it for document generation, template-based reports, and content management workflows.

## Use Cases

- Automated document generation
- Template-based reporting
- Content extraction
- Contract and proposal creation

## Installation

```bash
pip install toolsconnector[gdocs]
```

Set your credentials:

```bash
export TC_GDOCS_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["gdocs"], credentials={"gdocs": "your-token"})

# Get a document by ID
result = kit.execute("gdocs_get_document", {"document_id": "doc-123"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["gdocs"], credentials={"gdocs": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["gdocs"], credentials={"gdocs": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### OAuth 2.0

1. Google Cloud Console
2. Credentials

[Get credentials &rarr;](https://console.cloud.google.com/apis/credentials)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("gdocs_get_document", {})
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

- Use batch operations (`batch_update`) for bulk operations instead of individual calls
- Rate limit is 300 requests/minute per project — use pagination and caching to minimize API calls
- Actions marked as destructive (`batch_update`, `create_document`, `insert_text`) cannot be undone — use with caution

## Related Connectors

- [Gcalendar](../gcalendar/) — Calendar
- [Gsheets](../gsheets/) — Spreadsheets
- [Gtasks](../gtasks/) — Task lists
- [Figma](../figma/) — Design

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
