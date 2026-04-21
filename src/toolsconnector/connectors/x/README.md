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

## Endpoints and scopes

All under base URL `https://api.x.com/2`.

| Action | Endpoint | OAuth 2.0 scopes |
|---|---|---|
| `get_me` | `GET /users/me` | `tweet.read users.read` |
| `create_tweet` | `POST /tweets` | `tweet.read tweet.write users.read` |
| `delete_tweet` | `DELETE /tweets/{id}` | `tweet.read tweet.write users.read` |
| `reply_to_tweet` | `POST /tweets` (with `reply.in_reply_to_tweet_id`) | `tweet.read tweet.write users.read` |
| `create_thread` | N × `POST /tweets` sequentially | `tweet.read tweet.write users.read` |
| `like_tweet` | `POST /users/{id}/likes` (body `{tweet_id}`) | `like.write` |
| `unlike_tweet` | `DELETE /users/{id}/likes/{tweet_id}` | `like.write` |
| `list_mentions` | `GET /users/{id}/mentions` | `tweet.read users.read` |
| `send_dm` | `POST /dm_conversations/with/{id}/messages` | `dm.write tweet.read users.read` |

Per the X API docs, `id` for `like_tweet` / `unlike_tweet` / `list_mentions` MUST be the authenticated user's ID — fetch it via `get_me` first.

## API tier policy

The X API has paid tiers (Free, Basic $100/mo, Pro, Enterprise) with different per-endpoint access and quotas. **The exact endpoint-to-tier mapping is set by X's commercial policy and changes over time** — it is NOT formally specified per-endpoint in the OpenAPI spec.

Historically:

- **Free tier** covers user-context write actions (post, reply, thread, like, unlike, delete) with a tight monthly write quota (~1,500/month).
- **Basic tier ($100/mo)** typically adds full read access (mentions timeline, search) and DMs.
- **Pro/Enterprise** raise quotas significantly.

This connector exposes the full API surface. When your tier doesn't allow an endpoint, X returns HTTP 403 with reason `client-not-enrolled` / `usage cap` / `client-forbidden`, which the connector maps to `PermissionDeniedError` with a clear hint pointing at https://developer.x.com/en/products/twitter-api.

## `create_thread` partial-failure semantics

`create_thread(texts)` posts N tweets sequentially via `POST /2/tweets`, each as a reply to the previous (X has no first-class "thread" endpoint). If a tweet mid-thread fails, the previously posted tweets remain published — there is no rollback.

The exception is re-raised, but the partial result is preserved on `e.details["posted_tweets"]` so callers can decide whether to accept a half-published thread or repost the missing tail.

## Reference docs

- [X API v2 Introduction](https://docs.x.com/x-api/introduction)
- [Create or edit a Post](https://docs.x.com/x-api/posts/creation-of-a-post)
- [Delete a Post](https://docs.x.com/x-api/posts/delete-post)
- [Like / Unlike](https://docs.x.com/x-api/posts/likes)
- [User mentions timeline](https://docs.x.com/x-api/users/get-mentions)
- [Send DM to user](https://docs.x.com/x-api/direct-messages/create-dm-message-by-participant-id)
- [GET /2/users/me](https://docs.x.com/x-api/users/user-lookup-me)

## Actions

<!-- ACTIONS_START -->
<!-- This section is auto-generated from the connector spec. Do not edit manually. -->
<!-- ACTIONS_END -->

## Tips

- Rate limit is Tier-dependent; Free: ~50 writes/day; Basic: ~17K writes/month — use pagination and caching to minimize API calls
- Actions marked as destructive (`create_thread`, `create_tweet`, `delete_tweet`) cannot be undone — use with caution

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
