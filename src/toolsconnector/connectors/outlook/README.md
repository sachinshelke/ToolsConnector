# Microsoft Outlook

> Email, calendar, and contacts via Microsoft Graph

| | |
|---|---|
| **Company** | Microsoft |
| **Category** | Communication |
| **Protocol** | REST |
| **Website** | [outlook.com](https://outlook.com) |
| **API Docs** | [learn.microsoft.com](https://learn.microsoft.com/en-us/graph/api/resources/mail-api-overview) |
| **Auth** | OAuth 2.0 (Microsoft Graph) |
| **Rate Limit** | 10,000 requests/10 minutes per app |
| **Pricing** | Included with Microsoft 365 |

---

## Overview

The Microsoft Graph Mail API provides access to Outlook email, calendar, and contacts. Read, send, and organize emails, manage calendar events, and work with contact data across Microsoft 365 accounts.

## Use Cases

- Email automation
- Calendar management
- Contact sync
- Meeting scheduling
- Email analytics

## Installation

```bash
pip install "toolsconnector[outlook]"
```

Set your credentials:

```bash
export TC_OUTLOOK_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["outlook"], credentials={"outlook": "your-token"})

# List email messages from a folder
result = kit.execute("outlook_list_messages", {"folder": "your-folder", "limit": 25})
print(result)
```

### MCP Server

```python
kit = ToolKit(["outlook"], credentials={"outlook": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["outlook"], credentials={"outlook": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### OAuth 2.0 (Microsoft Graph)

1. Create an account at [Microsoft Outlook](https://outlook.com)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("outlook_list_messages", {})
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

- Use `search_messages` for filtered queries and `list_attachments` for paginated browsing
- Rate limit is 10,000 requests/10 minutes per app — use pagination and caching to minimize API calls
- Actions marked as destructive (`create_calendar_event`, `create_contact`, `create_folder`) cannot be undone — use with caution
- This connector has 23 actions — use `ToolKit(include_actions=[...])` to expose only what your agent needs

## Related Connectors

- [Gmail](../gmail/) — Email automation
- [Slack](../slack/) — Team messaging
- [Discord](../discord/) — Community messaging
- [Teams](../teams/) — Microsoft collaboration

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
