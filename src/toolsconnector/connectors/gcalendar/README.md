# Google Calendar

> Schedule events, manage calendars, check availability

| | |
|---|---|
| **Company** | Google |
| **Category** | Productivity |
| **Protocol** | REST |
| **Website** | [calendar.google.com](https://calendar.google.com) |
| **API Docs** | [developers.google.com](https://developers.google.com/calendar/api/v3/reference) |
| **Auth** | OAuth 2.0, Service Account |
| **Rate Limit** | 500 requests/100 seconds per user |
| **Pricing** | Free with Google account |

---

## Overview

The Google Calendar API lets you create, modify, and query calendar events. Check free/busy status for scheduling, manage calendar sharing and access control, and build scheduling automation for teams and organizations.

## Use Cases

- Meeting scheduling automation
- Availability checking
- Calendar sync across platforms
- Event reminders and notifications
- Resource booking systems

## Installation

```bash
pip install toolsconnector[gcalendar]
```

Set your credentials:

```bash
export TC_GCALENDAR_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["gcalendar"], credentials={"gcalendar": "your-token"})

# List calendar events
result = kit.execute("gcalendar_list_events", {"calendar_id": "primary", "time_min": "your-time_min"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["gcalendar"], credentials={"gcalendar": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["gcalendar"], credentials={"gcalendar": "your-token"})
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
    result = kit.execute("gcalendar_list_events", {})
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

- Rate limit is 500 requests/100 seconds per user — use pagination and caching to minimize API calls
- Actions marked as destructive (`add_calendar_acl`, `clear_calendar`, `create_calendar`) cannot be undone — use with caution

## Related Connectors

- [Gdocs](../gdocs/) — Documents
- [Gsheets](../gsheets/) — Spreadsheets
- [Gtasks](../gtasks/) — Task lists
- [Figma](../figma/) — Design

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
