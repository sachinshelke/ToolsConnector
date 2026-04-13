# Calendly

> Scheduling automation for meetings and events

| | |
|---|---|
| **Company** | Calendly LLC |
| **Category** | Productivity |
| **Protocol** | REST |
| **Website** | [calendly.com](https://calendly.com) |
| **API Docs** | [developer.calendly.com](https://developer.calendly.com/api-docs) |
| **Auth** | Personal Access Token, OAuth 2.0 |
| **Rate Limit** | 200 requests/minute |
| **Pricing** | Free tier, Standard from $10/seat/month |

---

## Overview

The Calendly API provides access to event types, scheduled events, invitees, and scheduling links. Automate meeting scheduling, sync calendar data, manage availability, and build custom booking experiences.

## Use Cases

- Meeting scheduling automation
- Calendar sync
- Event analytics
- Custom booking pages
- Sales pipeline integration

## Installation

```bash
pip install toolsconnector[calendly]
```

Set your credentials:

```bash
export TC_CALENDLY_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["calendly"], credentials={"calendly": "your-token"})

# Get the current authenticated user
result = kit.execute("calendly_get_current_user", {})
print(result)
```

### MCP Server

```python
kit = ToolKit(["calendly"], credentials={"calendly": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["calendly"], credentials={"calendly": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### Personal Access Token

1. Create an account at [Calendly](https://calendly.com)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://calendly.com/integrations/api_webhooks)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("calendly_get_current_user", {})
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

- Rate limit is 200 requests/minute — use pagination and caching to minimize API calls
- Actions marked as destructive (`cancel_event`, `cancel_invitee`, `create_invitee`) cannot be undone — use with caution
- Use cursor-based pagination for large result sets — pass the `cursor` from previous responses

## Related Connectors

- [Gcalendar](../gcalendar/) — Calendar
- [Gdocs](../gdocs/) — Documents
- [Gsheets](../gsheets/) — Spreadsheets
- [Gtasks](../gtasks/) — Task lists

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
