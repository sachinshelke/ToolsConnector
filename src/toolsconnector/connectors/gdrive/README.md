# Google Drive

> Store, share, and collaborate on files

| | |
|---|---|
| **Company** | Google |
| **Category** | Storage |
| **Protocol** | REST |
| **Website** | [drive.google.com](https://drive.google.com) |
| **API Docs** | [developers.google.com](https://developers.google.com/drive/api/reference/rest/v3) |
| **Auth** | OAuth 2.0, Service Account |
| **Rate Limit** | 12,000 requests/minute per project |
| **Pricing** | Free (15GB), Google Workspace plans for more |

---

## Overview

The Google Drive API provides programmatic access to Google Drive files and folders. Upload, download, search, and organize files. Manage sharing permissions and collaborate with comments. Export Google Docs/Sheets/Slides to PDF, DOCX, and other formats.

## Use Cases

- File backup and sync
- Document management systems
- Automated report generation
- File sharing workflows
- Content migration

## Installation

```bash
pip install toolsconnector[gdrive]
```

Set your credentials:

```bash
export TC_GDRIVE_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["gdrive"], credentials={"gdrive": "your-token"})

# List files in Google Drive
result = kit.execute("gdrive_list_files", {"page_size": 20, "order_by": "modifiedTime desc"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["gdrive"], credentials={"gdrive": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["gdrive"], credentials={"gdrive": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### OAuth 2.0

1. Google Cloud Console
2. APIs & Services
3. Credentials

[Get credentials &rarr;](https://console.cloud.google.com/apis/credentials)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("gdrive_list_files", {})
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

- Use `search_files` for filtered queries and `list_comments` for paginated browsing
- Rate limit is 12,000 requests/minute per project — use pagination and caching to minimize API calls
- Actions marked as destructive (`create_comment`, `delete_comment`, `delete_file`) cannot be undone — use with caution
- This connector has 22 actions — use `ToolKit(include_actions=[...])` to expose only what your agent needs

## Related Connectors

- [S3](../s3/) — AWS storage

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
