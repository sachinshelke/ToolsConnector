# GitHub

> Code hosting, issues, PRs, and CI/CD

| | |
|---|---|
| **Company** | Microsoft (GitHub Inc.) |
| **Category** | Code Platform |
| **Protocol** | REST |
| **Website** | [github.com](https://github.com) |
| **API Docs** | [docs.github.com](https://docs.github.com/en/rest) |
| **Auth** | Personal Access Token, OAuth 2.0, GitHub App |
| **Rate Limit** | 5,000 requests/hour authenticated |
| **Pricing** | Free for public repos, Teams from $4/user/month |

---

## Overview

The GitHub REST API provides access to repositories, issues, pull requests, commits, releases, and more. Automate code reviews, manage CI/CD workflows, track issues, and build developer tools that integrate with the GitHub ecosystem.

## Use Cases

- CI/CD automation
- Issue tracking and triage
- Code review workflows
- Release management
- Developer analytics

## Installation

```bash
pip install "toolsconnector[github]"
```

Set your credentials:

```bash
export TC_GITHUB_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["github"], credentials={"github": "your-token"})

# List repositories for a user or organisation
result = kit.execute("github_list_repos", {"org": "your-org", "user": "your-user"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["github"], credentials={"github": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["github"], credentials={"github": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### Personal Access Token

1. Settings
2. Developer Settings
3. Personal Access Tokens

[Get credentials &rarr;](https://github.com/settings/tokens)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("github_list_repos", {})
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

- Use `search_code` for filtered queries and `list_branches` for paginated browsing
- Rate limit is 5,000 requests/hour authenticated — use pagination and caching to minimize API calls
- Actions marked as destructive (`create_comment`, `create_gist`, `create_issue`) cannot be undone — use with caution
- This connector has 37 actions — use `ToolKit(include_actions=[...])` to expose only what your agent needs

## Related Connectors

- [Gitlab](../gitlab/) — DevOps platform

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
