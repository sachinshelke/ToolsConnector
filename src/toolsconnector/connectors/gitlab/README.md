# GitLab

> DevOps platform with Git, CI/CD, and issue tracking

| | |
|---|---|
| **Company** | GitLab Inc. |
| **Category** | Code Platform |
| **Protocol** | REST |
| **Website** | [gitlab.com](https://gitlab.com) |
| **API Docs** | [docs.gitlab.com](https://docs.gitlab.com/api/rest/) |
| **Auth** | Personal Access Token, OAuth 2.0 |
| **Rate Limit** | 2,000 requests/minute authenticated |
| **Pricing** | Free tier, Premium from $29/user/month |

---

## Overview

The GitLab REST API provides access to projects, merge requests, issues, pipelines, and CI/CD. Manage the full DevOps lifecycle from a single platform. Supports both GitLab.com and self-hosted instances.

## Use Cases

- CI/CD pipeline management
- Merge request automation
- Issue tracking
- Release management
- Self-hosted DevOps

## Installation

```bash
pip install toolsconnector[gitlab]
```

Set your credentials:

```bash
export TC_GITLAB_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["gitlab"], credentials={"gitlab": "your-token"})

# List issues for a GitLab project
result = kit.execute("gitlab_list_issues", {"project_id": "proj-123", "state": "open", "labels": "your-labels"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["gitlab"], credentials={"gitlab": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["gitlab"], credentials={"gitlab": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### Personal Access Token

1. Preferences
2. Access Tokens
3. Create

[Get credentials &rarr;](https://gitlab.com/-/user_settings/personal_access_tokens)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("gitlab_list_issues", {})
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

- Rate limit is 2,000 requests/minute authenticated — use pagination and caching to minimize API calls
- Actions marked as destructive (`create_branch`, `create_comment`, `create_issue`) cannot be undone — use with caution
- This connector has 21 actions — use `ToolKit(include_actions=[...])` to expose only what your agent needs

## Related Connectors

- [Github](../github/) — Code hosting

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
