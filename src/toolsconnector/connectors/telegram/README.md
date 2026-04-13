# Telegram

> Bot API for messaging and group management

| | |
|---|---|
| **Company** | Telegram FZ-LLC |
| **Category** | Communication |
| **Protocol** | REST |
| **Website** | [telegram.org](https://telegram.org) |
| **API Docs** | [core.telegram.org](https://core.telegram.org/bots/api) |
| **Auth** | Bot Token |
| **Rate Limit** | 30 messages/second (group), 1 msg/sec (per chat) |
| **Pricing** | Free |

---

## Overview

The Telegram Bot API lets you send and receive messages, manage groups and channels, handle inline queries, and create interactive bot experiences. Build notification bots, customer support flows, and command-driven automation.

## Use Cases

- Notification bots
- Group management
- Inline bot interactions
- Customer support
- Automated responses

## Installation

```bash
pip install toolsconnector[telegram]
```

Set your credentials:

```bash
export TC_TELEGRAM_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["telegram"], credentials={"telegram": "your-token"})

# Send a text message to a chat
result = kit.execute("telegram_send_message", {"chat_id": "your-chat_id", "text": "Hello!", "parse_mode": "your-parse_mode"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["telegram"], credentials={"telegram": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["telegram"], credentials={"telegram": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### Bot Token

1. Create an account at [Telegram](https://telegram.org)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://t.me/BotFather)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("telegram_send_message", {})
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

- Rate limit is 30 messages/second (group), 1 msg/sec (per chat) — use pagination and caching to minimize API calls
- Actions marked as destructive (`ban_chat_member`, `delete_message`, `leave_chat`) cannot be undone — use with caution
- This connector has 26 actions — use `ToolKit(include_actions=[...])` to expose only what your agent needs

## Related Connectors

- [Gmail](../gmail/) — Email automation
- [Slack](../slack/) — Team messaging
- [Discord](../discord/) — Community messaging
- [Teams](../teams/) — Microsoft collaboration

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
