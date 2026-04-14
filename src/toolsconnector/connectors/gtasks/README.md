# Google Tasks

> Manage task lists and to-do items

| | |
|---|---|
| **Company** | Google |
| **Category** | Productivity |
| **Protocol** | REST |
| **Website** | [tasks.google.com](https://tasks.google.com) |
| **API Docs** | [developers.google.com](https://developers.google.com/tasks/reference/rest) |
| **Auth** | OAuth 2.0 |
| **Rate Limit** | 300 requests/minute per project |
| **Pricing** | Free with Google account |

---

## Overview

The Google Tasks API provides access to task lists and individual tasks. Create, update, complete, and organize tasks programmatically. Integrates naturally with Google Calendar and Gmail for productivity workflows.

## Use Cases

- Task automation
- Project tracking
- To-do list sync
- Workflow triggers on task completion

## Installation

```bash
pip install "toolsconnector[gtasks]"
```

Set your credentials:

```bash
export TC_GTASKS_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["gtasks"], credentials={"gtasks": "your-token"})

# List tasks in a task list
result = kit.execute("gtasks_list_tasks", {"task_list_id": "your-task_list_id", "completed": "your-completed", "due_min": "your-due_min"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["gtasks"], credentials={"gtasks": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["gtasks"], credentials={"gtasks": "your-token"})
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
    result = kit.execute("gtasks_list_tasks", {})
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

- Rate limit is 300 requests/minute per project — use pagination and caching to minimize API calls
- Actions marked as destructive (`clear_completed`, `complete_task`, `create_task`) cannot be undone — use with caution

## Related Connectors

- [Gcalendar](../gcalendar/) — Calendar
- [Gdocs](../gdocs/) — Documents
- [Gsheets](../gsheets/) — Spreadsheets
- [Figma](../figma/) — Design

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
