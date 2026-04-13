# Microsoft Teams

> Team collaboration, messaging, and meetings

| | |
|---|---|
| **Company** | Microsoft |
| **Category** | Communication |
| **Protocol** | REST |
| **Website** | [teams.microsoft.com](https://teams.microsoft.com) |
| **API Docs** | [learn.microsoft.com](https://learn.microsoft.com/en-us/graph/api/resources/teams-api-overview) |
| **Auth** | OAuth 2.0 (Microsoft Graph) |
| **Rate Limit** | Varies by endpoint |
| **Pricing** | Included with Microsoft 365 |

---

## Overview

The Microsoft Teams API (via Microsoft Graph) provides access to teams, channels, messages, and members. Send messages, manage team membership, create channels, and build collaboration workflows for Microsoft 365.

## Use Cases

- Team messaging automation
- Channel management
- Meeting scheduling
- Notification bots
- Workflow integrations

## Installation

```bash
pip install toolsconnector[teams]
```

Set your credentials:

```bash
export TC_TEAMS_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["teams"], credentials={"teams": "your-token"})

# List messages in a Teams channel
result = kit.execute("teams_list_messages", {"team_id": "T01234567", "channel_id": "C01234567", "limit": 50, "page_url": "your-page_url"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["teams"], credentials={"teams": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["teams"], credentials={"teams": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### OAuth 2.0 (Microsoft Graph)

1. Create an account at [Microsoft Teams](https://teams.microsoft.com)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("teams_list_messages", {})
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

- Rate limit is Varies by endpoint — use pagination and caching to minimize API calls
- Actions marked as destructive (`add_member`, `delete_channel`, `remove_member`) cannot be undone — use with caution

## Related Connectors

- [Gmail](../gmail/) — Email automation
- [Slack](../slack/) — Team messaging
- [Discord](../discord/) — Community messaging
- [Telegram](../telegram/) — Bot messaging

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
