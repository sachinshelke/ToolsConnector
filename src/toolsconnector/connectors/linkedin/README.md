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

## What actually works for standard BYOK tokens ✅

Three actions are **live-verified** against the real LinkedIn API (2026-04). Any developer can enable these by creating a [LinkedIn Developer App](https://www.linkedin.com/developers/apps) and adding the two self-serve products listed below — no partnership approval needed.

| Action | Endpoint | Scope | Status |
|---|---|---|---|
| `get_profile` | `GET /v2/userinfo` | `openid profile email` (Sign in with LinkedIn using OpenID Connect) | ✅ **Live verified** |
| `create_post` | `POST /rest/posts` | `w_member_social` (Share on LinkedIn) | ✅ **Live verified** |
| `delete_post` | `DELETE /rest/posts/{urn}` | `w_member_social` (Share on LinkedIn) | ✅ **Live verified** |

## What requires LinkedIn Partner Program approval ⚠️

LinkedIn's public docs say these need only `w_member_social` or `r_member_social`, but **live testing reveals they are actually gated behind the LinkedIn Partner Program** — requests with standard self-serve tokens return HTTP 403 with error codes like `partnerApiReactions.CREATE.20260401` or `partnerApiSocialActions.CREATE.20260401`. This connector exposes the endpoints regardless so approved partners can use them; standard tokens hit `PermissionDeniedError` with a clear hint pointing at the Partner Program.

| Action | Endpoint | LinkedIn's 403 error code |
|---|---|---|
| `create_comment` | `POST /rest/socialActions/{urn}/comments` | `partnerApiSocialActions.CREATE` |
| `react_to_post` | `POST /rest/reactions?actor={urn}` | `partnerApiReactions.CREATE` |
| `list_comments` | `GET /rest/socialActions/{urn}/comments` | `partnerApiSocialActions.READ` (needs restricted `r_member_social`) |
| `get_post` | `GET /rest/posts/{urn}` | `r_member_social` (restricted) |
| `list_my_posts` | `GET /rest/posts?q=author&author={urn}` | `r_member_social` (restricted) |

To get LinkedIn Partner Program access: https://www.linkedin.com/business/partner-programs/marketing

## Not supported (Partner Program required)

These cannot be exposed under standard BYOK access at all — no endpoints are included in the connector:

| Capability | Why it's not implemented |
|---|---|
| **DMs / Messaging API** | Requires LinkedIn Partner Program approval. Standard developer apps cannot send messages on behalf of members. |
| **Mentions / Notifications** | The Notifications API is partner-only. There is no public BYOK endpoint to read mentions. |
| **Image / Video / Document uploads** | Require a separate multi-step Vector Asset upload flow. Use the `content` parameter on `create_post` if you already have an asset URN. |

## Token expiry

LinkedIn access tokens expire **60 days** after issue. When that happens, the connector raises `TokenExpiredError` with a hint to regenerate at https://www.linkedin.com/developers/apps. Plan for token rotation in production.

## Versioned API

This connector targets LinkedIn's Versioned API (`/rest/*`). The `Linkedin-Version` header is pinned to `202604` (the latest version in the documented support range as of 2026-04). LinkedIn versions are valid for ~12 months — when bumping to a newer version, check the [migration guide](https://learn.microsoft.com/en-us/linkedin/marketing/integrations/migrations) for any breaking schema changes.

## Reference docs

- [Sign In with LinkedIn using OpenID Connect](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/sign-in-with-linkedin-v2)
- [Share on LinkedIn (consumer overview)](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/share-on-linkedin)
- [Posts API (Versioned)](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api)
- [Comments API](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/comments-api)
- [Reactions API](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/reactions-api)

## Actions

<!-- ACTIONS_START -->
<!-- This section is auto-generated from the connector spec. Do not edit manually. -->
<!-- ACTIONS_END -->

## Tips

- Rate limit is ~100 calls/day per user (member-tier app) — use pagination and caching to minimize API calls
- Actions marked as destructive (`create_comment`, `create_post`, `delete_post`) cannot be undone — use with caution

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
