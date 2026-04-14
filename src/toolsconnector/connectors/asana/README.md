# Asana

> Work management and project tracking for teams

| | |
|---|---|
| **Company** | Asana Inc. |
| **Category** | Project Management |
| **Protocol** | REST |
| **Website** | [asana.com](https://asana.com) |
| **API Docs** | [developers.asana.com](https://developers.asana.com/reference/rest-api-reference) |
| **Auth** | Personal Access Token, OAuth 2.0 |
| **Rate Limit** | 150 requests/minute |
| **Pricing** | Free tier, Premium from $10.99/user/month |

---

## Overview

The Asana API lets you manage tasks, projects, sections, and teams programmatically. Create workflows, track work status, manage assignments, and build custom integrations with Asana's work management platform.

## Use Cases

- Task automation
- Project tracking dashboards
- Cross-tool workflow sync
- Sprint management
- Team workload reporting

## Installation

```bash
pip install "toolsconnector[asana]"
```

Set your credentials:

```bash
export TC_ASANA_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["asana"], credentials={"asana": "your-token"})

# List tasks in a project
result = kit.execute("asana_list_tasks", {"project_gid": "your-project_gid", "limit": 50, "offset": "your-offset"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["asana"], credentials={"asana": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["asana"], credentials={"asana": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### Personal Access Token

1. Create an account at [Asana](https://asana.com)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://app.asana.com/0/my-apps)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("asana_list_tasks", {})
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

- Use `search_tasks` for filtered queries and `list_attachments` for paginated browsing
- Rate limit is 150 requests/minute — use pagination and caching to minimize API calls
- Actions marked as destructive (`add_comment`, `add_dependencies`, `add_followers`) cannot be undone — use with caution
- This connector has 38 actions — use `ToolKit(include_actions=[...])` to expose only what your agent needs

## Related Connectors

- [Jira](../jira/) — Issue tracking
- [Linear](../linear/) — Modern issue tracker
- [Trello](../trello/) — Kanban boards

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
