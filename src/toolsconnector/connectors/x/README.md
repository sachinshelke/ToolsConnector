# X (Twitter)

> Post tweets, threads, replies — and read mentions/DMs (Basic tier)

| | |
|---|---|
| **Company** | X Corp |
| **Category** | Social |
| **Protocol** | REST |
| **Website** | [x.com](https://x.com) |
| **API Docs** | [developer.x.com](https://developer.x.com/en/docs/x-api) |
| **Auth** | OAuth 2.0 Bearer Token |
| **Rate Limit** | Tier-dependent; Free: ~50 writes/day; Basic: ~17K writes/month |
| **Pricing** | Free tier (~1,500 tweets/mo); Basic $100/mo (mentions+DMs); Pro $5,000/mo |

---

## Overview

The X (formerly Twitter) API v2 supports tweet creation, threading, replies, likes, and DM/mention reads. The API is tiered: the Free tier covers all write actions (~1,500 tweets/month). Read of mentions and DM operations require Basic tier ($100/month) or higher. This connector exposes endpoints across tiers; per-action docstrings declare the required tier so AI agents can surface the requirement before attempting a call.

## Use Cases

- Personal brand automation
- PR/announcement workflows
- Reply bots
- Cross-posting from blogs
- Thread automation

## Installation

```bash
pip install "toolsconnector[x]"
```

Set your credentials:

```bash
export TC_X_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["x"], credentials={"x": "your-token"})

# Get the authenticated X user's profile (Free tier)
result = kit.execute("x_get_me", {})
print(result)
```

### MCP Server

```python
kit = ToolKit(["x"], credentials={"x": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["x"], credentials={"x": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### OAuth 2.0 Bearer Token

1. X Developer Portal
2. Project
3. User authentication settings
4. OAuth 2.0
5. Generate user-context access token

[Get credentials &rarr;](https://developer.x.com/en/portal/dashboard)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("x_get_me", {})
except RateLimitError as e:
    print(f"Rate limited. Retry in {e.retry_after_seconds}s")
except AuthError as e:
    print(f"Auth failed: {e.suggestion}")
```

## API tier requirements

The X API is **tiered** — different endpoints require different paid tiers. This connector exposes endpoints across tiers so any token works for the actions it covers; tier-gated endpoints raise a clear `PermissionDeniedError` on Free-tier accounts.

| Action | Tier required |
|---|---|
| `get_me` | Free |
| `create_tweet` | Free |
| `delete_tweet` | Free |
| `create_thread` | Free (1 write per tweet — counts against quota) |
| `reply_to_tweet` | Free |
| `like_tweet` / `unlike_tweet` | Free |
| `list_mentions` | **Basic ($100/mo) or higher** |
| `send_dm` | **Basic ($100/mo) or higher** |

Each action's docstring prefixes the required tier so AI agents can surface the requirement before attempting a call.

## `create_thread` partial-failure semantics

`create_thread(texts)` posts N tweets sequentially, each as a reply to the previous. If a tweet mid-thread fails (rate limit, network, 5xx), the previously posted tweets remain published — there is no rollback.

The exception is re-raised, but the partial result is preserved on `e.details["posted_tweets"]` so callers can decide whether to accept a half-published thread or repost the missing tail.

## Actions

<!-- ACTIONS_START -->
<!-- This section is auto-generated from the connector spec. Do not edit manually. -->
<!-- ACTIONS_END -->

## Tips

- Rate limit is Tier-dependent; Free: ~50 writes/day; Basic: ~17K writes/month — use pagination and caching to minimize API calls
- Actions marked as destructive (`create_thread`, `create_tweet`, `delete_tweet`) cannot be undone — use with caution

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
