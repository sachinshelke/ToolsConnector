# Linear

> Streamlined issue tracking for software teams

| | |
|---|---|
| **Company** | Linear Inc. |
| **Category** | Project Management |
| **Protocol** | GraphQL |
| **Website** | [linear.app](https://linear.app) |
| **API Docs** | [developers.linear.app](https://developers.linear.app/docs/graphql/working-with-the-graphql-api) |
| **Auth** | API Key, OAuth 2.0 |
| **Rate Limit** | 400 requests/minute |
| **Pricing** | Free tier, Plus from $8/user/month |

---

## Overview

The Linear GraphQL API provides access to issues, projects, cycles, teams, and labels. Track bugs and features, manage sprints, automate workflows, and build integrations with Linear's modern project management platform.

## Use Cases

- Issue tracking
- Sprint management
- Bug triage automation
- Development workflow
- Cross-tool project sync

## Installation

```bash
pip install toolsconnector[linear]
```

Set your credentials:

```bash
export TC_LINEAR_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["linear"], credentials={"linear": "your-token"})

# List issues with optional team and state filters
result = kit.execute("linear_list_issues", {"team_id": "T01234567", "state": "open"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["linear"], credentials={"linear": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["linear"], credentials={"linear": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### API Key

1. Create an account at [Linear](https://linear.app)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://linear.app/settings/api)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("linear_list_issues", {})
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

- Use `search_issues` for filtered queries and `list_cycles` for paginated browsing
- Rate limit is 400 requests/minute — use pagination and caching to minimize API calls
- Actions marked as destructive (`add_comment`, `create_issue`, `create_label`) cannot be undone — use with caution
- Use cursor-based pagination for large result sets — pass the `cursor` from previous responses

## Related Connectors

- [Jira](../jira/) — Issue tracking
- [Asana](../asana/) — Work management
- [Trello](../trello/) — Kanban boards

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
