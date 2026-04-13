# Discord

> Messaging, voice, and community management

| | |
|---|---|
| **Company** | Discord Inc. |
| **Category** | Communication |
| **Protocol** | REST |
| **Website** | [discord.com](https://discord.com) |
| **API Docs** | [discord.com](https://discord.com/developers/docs) |
| **Auth** | Bot Token, OAuth 2.0 |
| **Rate Limit** | 50 requests/second global |
| **Pricing** | Free, Nitro from $9.99/month |

---

## Overview

The Discord API provides access to Discord servers (guilds), channels, messages, and members. Build bots that moderate communities, send notifications, manage roles, and create interactive experiences. Supports bot tokens and OAuth 2.0.

## Use Cases

- Community moderation bots
- Server management automation
- Notification systems
- Gaming integrations
- Event management

## Installation

```bash
pip install toolsconnector[discord]
```

Set your credentials:

```bash
export TC_DISCORD_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["discord"], credentials={"discord": "your-token"})

# List messages in a channel
result = kit.execute("discord_list_messages", {"channel_id": "C01234567", "limit": 50, "before": "your-before"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["discord"], credentials={"discord": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["discord"], credentials={"discord": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### Bot Token

1. Developer Portal
2. New Application
3. Bot Token

[Get credentials &rarr;](https://discord.com/developers/applications)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("discord_list_messages", {})
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

- Rate limit is 50 requests/second global — use pagination and caching to minimize API calls
- Actions marked as destructive (`add_member_role`, `ban_member`, `create_channel`) cannot be undone — use with caution
- This connector has 25 actions — use `ToolKit(include_actions=[...])` to expose only what your agent needs

## Related Connectors

- [Gmail](../gmail/) — Email automation
- [Slack](../slack/) — Team messaging
- [Teams](../teams/) — Microsoft collaboration
- [Telegram](../telegram/) — Bot messaging

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
