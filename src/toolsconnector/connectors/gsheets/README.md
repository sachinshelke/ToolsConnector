# Google Sheets

> Read, write, and format spreadsheet data

| | |
|---|---|
| **Company** | Google |
| **Category** | Productivity |
| **Protocol** | REST |
| **Website** | [sheets.google.com](https://sheets.google.com) |
| **API Docs** | [developers.google.com](https://developers.google.com/sheets/api/reference/rest) |
| **Auth** | OAuth 2.0, Service Account |
| **Rate Limit** | 300 requests/minute per project |
| **Pricing** | Free with Google account |

---

## Overview

The Google Sheets API provides full access to spreadsheet data and structure. Read and write cell values, create and format sheets, apply batch operations, and use Sheets as a lightweight database or reporting layer for your applications.

## Use Cases

- Data entry and extraction
- Automated reporting
- Spreadsheet as database
- Data pipelines and ETL
- Budget and inventory tracking

## Installation

```bash
pip install "toolsconnector[gsheets]"
```

Set your credentials:

```bash
export TC_GSHEETS_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["gsheets"], credentials={"gsheets": "your-token"})

# Get values from a range
result = kit.execute("gsheets_get_values", {"spreadsheet_id": "sheet-123", "range": "your-range"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["gsheets"], credentials={"gsheets": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["gsheets"], credentials={"gsheets": "your-token"})
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
    result = kit.execute("gsheets_get_values", {})
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

- Use batch operations (`batch_get_values`, `batch_update_spreadsheet`, `batch_update_values`) for bulk operations instead of individual calls
- Rate limit is 300 requests/minute per project — use pagination and caching to minimize API calls
- Actions marked as destructive (`add_sheet`, `append_values`, `batch_update_spreadsheet`) cannot be undone — use with caution

## Related Connectors

- [Gcalendar](../gcalendar/) — Calendar
- [Gdocs](../gdocs/) — Documents
- [Gtasks](../gtasks/) — Task lists
- [Figma](../figma/) — Design

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
