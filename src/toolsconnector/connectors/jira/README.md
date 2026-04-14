# Jira

> Project tracking, issue management, and agile boards

| | |
|---|---|
| **Company** | Atlassian |
| **Category** | Project Management |
| **Protocol** | REST |
| **Website** | [www.atlassian.com/software/jira](https://www.atlassian.com/software/jira) |
| **API Docs** | [developer.atlassian.com](https://developer.atlassian.com/cloud/jira/platform/rest/v3/) |
| **Auth** | Basic Auth (email:api_token), OAuth 2.0 |
| **Rate Limit** | 100 requests/minute |
| **Pricing** | Free up to 10 users, Standard from $8.15/user/month |

---

## Overview

The Jira REST API provides access to issues, projects, sprints, boards, and workflows. Search with JQL, manage issue transitions, track time with worklogs, and automate agile project management across teams.

## Use Cases

- Issue tracking automation
- Sprint planning
- Bug triage workflows
- Cross-tool project sync
- Custom reporting

## Installation

```bash
pip install "toolsconnector[jira]"
```

Set your credentials:

```bash
export TC_JIRA_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["jira"], credentials={"jira": "your-token"})

# List projects accessible to the user
result = kit.execute("jira_list_projects", {"limit": 50, "start_at": 0})
print(result)
```

### MCP Server

```python
kit = ToolKit(["jira"], credentials={"jira": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["jira"], credentials={"jira": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### Basic Auth (email:api_token)

1. Account Settings
2. Security
3. API Tokens

[Get credentials &rarr;](https://id.atlassian.com/manage-profile/security/api-tokens)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("jira_list_projects", {})
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

- Use `search_issues` for filtered queries and `list_boards` for paginated browsing
- Rate limit is 100 requests/minute — use pagination and caching to minimize API calls
- Actions marked as destructive (`add_attachment`, `add_comment`, `add_worklog`) cannot be undone — use with caution
- This connector has 28 actions — use `ToolKit(include_actions=[...])` to expose only what your agent needs

## Related Connectors

- [Asana](../asana/) — Work management
- [Linear](../linear/) — Modern issue tracker
- [Trello](../trello/) — Kanban boards

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
