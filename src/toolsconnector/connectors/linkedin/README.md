# LinkedIn

> Post, comment, and react on the world's largest professional network

| | |
|---|---|
| **Company** | Microsoft (LinkedIn) |
| **Category** | Social |
| **Protocol** | REST |
| **Website** | [linkedin.com](https://linkedin.com) |
| **API Docs** | [learn.microsoft.com](https://learn.microsoft.com/linkedin/) |
| **Auth** | OAuth 2.0 Bearer Token |
| **Rate Limit** | ~100 calls/day per user (member-tier app) |
| **Pricing** | API access free; tokens expire after 60 days |

---

## Overview

The LinkedIn Marketing & Member APIs let you publish posts to a user's personal feed, comment on existing posts, and add reactions. Uses OAuth 2.0 with member-level scopes (w_member_social, r_member_social). DMs and mentions are NOT included — those endpoints require LinkedIn Partner Program approval (a contract, not OAuth scopes) and cannot be used with standard BYOK access.

## Use Cases

- Personal brand automation
- Thought leadership pipelines
- PR and announcement workflows
- Cross-posting from blogs
- Engagement automation

## Installation

```bash
pip install "toolsconnector[linkedin]"
```

Set your credentials:

```bash
export TC_LINKEDIN_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["linkedin"], credentials={"linkedin": "your-token"})

# Get a single LinkedIn post by URN
result = kit.execute("linkedin_get_post", {"urn": "your-urn"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["linkedin"], credentials={"linkedin": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["linkedin"], credentials={"linkedin": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### OAuth 2.0 Bearer Token

1. LinkedIn Developers
2. Apps
3. Create app
4. Auth
5. Generate token (60-day expiry)

[Get credentials &rarr;](https://www.linkedin.com/developers/apps)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("linkedin_get_post", {})
except RateLimitError as e:
    print(f"Rate limited. Retry in {e.retry_after_seconds}s")
except AuthError as e:
    print(f"Auth failed: {e.suggestion}")
```

## Not Supported

Some LinkedIn capabilities cannot be exposed under standard BYOK OAuth — they require a contractual relationship with LinkedIn (the **Partner Program**), not a developer token:

| Capability | Why it's not implemented |
|---|---|
| **DMs / Messaging API** | Requires LinkedIn Partner Program approval. Standard developer apps cannot send messages on behalf of members. |
| **Mentions / Notifications** | The Notifications API is partner-only. There is no public BYOK endpoint to read mentions. |

If your use case requires these, the path is to apply to the LinkedIn Partner Program directly — once approved, you can build on top of those APIs separately.

## Token expiry

LinkedIn access tokens expire **60 days** after issue. When that happens, this connector raises `TokenExpiredError` with a hint to regenerate at https://www.linkedin.com/developers/apps. Plan for token rotation in production.

## API surface

This connector deliberately mixes two LinkedIn API versions:

- `/rest/posts` (newer, sent with `LinkedIn-Version: 202506`) — for `create_post`, `delete_post`, `get_post`, `list_my_posts`. This is LinkedIn's documented forward path.
- `/v2/socialActions/{urn}` (legacy v2) — for `create_comment`, `list_comments`, `react_to_post`. No `/rest` equivalent exists yet.
- `/v2/userinfo` (OIDC) — for `get_profile`. Most reliable user-identity endpoint across versions.

Each action's docstring documents which surface it targets.

## Actions

<!-- ACTIONS_START -->
<!-- This section is auto-generated from the connector spec. Do not edit manually. -->
<!-- ACTIONS_END -->

## Tips

- Rate limit is ~100 calls/day per user (member-tier app) — use pagination and caching to minimize API calls
- Actions marked as destructive (`create_comment`, `create_post`, `delete_post`) cannot be undone — use with caution

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
