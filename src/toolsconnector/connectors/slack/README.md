# Slack

> Team messaging, channels, and collaboration

| | |
|---|---|
| **Company** | Salesforce (Slack Technologies) |
| **Category** | Communication |
| **Protocol** | REST |
| **Website** | [slack.com](https://slack.com) |
| **API Docs** | [api.slack.com](https://api.slack.com/methods) |
| **Auth** | OAuth 2.0, Bot Token |
| **Rate Limit** | 1 request/second (Tier 2) |
| **Pricing** | Free tier available, Pro from $8.75/user/month |

---

## Overview

The Slack Web API provides comprehensive access to Slack workspaces. Send and manage messages, create and manage channels, upload files, manage users, set reminders, and build interactive bot experiences. Supports both bot tokens and user tokens.

## Use Cases

- Team notifications and alerts
- Customer support bots
- DevOps alerting
- Workflow automation
- Internal tooling

## Installation

```bash
pip install "toolsconnector[slack]"
```

Set your credentials:

```bash
export TC_SLACK_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["slack"], credentials={"slack": "your-token"})

# List messages in a channel
result = kit.execute("slack_list_messages", {"channel": "general", "limit": 100, "cursor": "your-cursor"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["slack"], credentials={"slack": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["slack"], credentials={"slack": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### OAuth 2.0

1. Slack API
2. Your Apps
3. Create New App
4. Bot Token

[Get credentials &rarr;](https://api.slack.com/apps)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("slack_list_messages", {})
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

- Use `search_messages` for filtered queries and `list_bookmarks` for paginated browsing
- Rate limit is 1 request/second (Tier 2) — use pagination and caching to minimize API calls
- Actions marked as destructive (`archive_channel`, `create_channel`, `create_usergroup`) cannot be undone — use with caution
- Use cursor-based pagination for large result sets — pass the `cursor` from previous responses

## Related Connectors

- [Gmail](../gmail/) — Email automation
- [Discord](../discord/) — Community messaging
- [Teams](../teams/) — Microsoft collaboration
- [Telegram](../telegram/) — Bot messaging

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
