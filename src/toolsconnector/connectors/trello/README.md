# Trello

> Visual project management with boards and cards

| | |
|---|---|
| **Company** | Atlassian |
| **Category** | Project Management |
| **Protocol** | REST |
| **Website** | [trello.com](https://trello.com) |
| **API Docs** | [developer.atlassian.com](https://developer.atlassian.com/cloud/trello/rest/api-group-actions/) |
| **Auth** | API Key + Token |
| **Rate Limit** | 100 requests/10 seconds per token |
| **Pricing** | Free tier, Standard from $5/user/month |

---

## Overview

The Trello API provides access to boards, lists, cards, members, and labels. Create and organize Kanban workflows, manage task cards, track progress, and build custom project management integrations.

## Use Cases

- Kanban workflow management
- Task tracking
- Team collaboration
- Sprint boards
- Content planning

## Installation

```bash
pip install "toolsconnector[trello]"
```

Set your credentials:

```bash
export TC_TRELLO_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["trello"], credentials={"trello": "your-token"})

# List boards for a Trello member
result = kit.execute("trello_list_boards", {"member": "me"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["trello"], credentials={"trello": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["trello"], credentials={"trello": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### API Key + Token

1. Create an account at [Trello](https://trello.com)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://trello.com/power-ups/admin)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("trello_list_boards", {})
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

- Rate limit is 100 requests/10 seconds per token — use pagination and caching to minimize API calls
- Actions marked as destructive (`add_attachment`, `add_comment`, `archive_card`) cannot be undone — use with caution
- This connector has 25 actions — use `ToolKit(include_actions=[...])` to expose only what your agent needs

## Related Connectors

- [Jira](../jira/) — Issue tracking
- [Asana](../asana/) — Work management
- [Linear](../linear/) — Modern issue tracker

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
