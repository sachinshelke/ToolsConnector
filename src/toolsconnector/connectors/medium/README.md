# Medium

> Publish articles to Medium profiles and publications (legacy tokens only)

| | |
|---|---|
| **Company** | A Medium Corporation |
| **Category** | Social |
| **Protocol** | REST |
| **Website** | [medium.com](https://medium.com) |
| **API Docs** | [github.com](https://github.com/Medium/medium-api-docs) |
| **Auth** | Bearer Token (Integration) |
| **Rate Limit** | Undocumented; conservative defaults applied |
| **Pricing** | Free; tokens are not reissued (API deprecated 2023) |

---

## Overview

The Medium REST API lets you publish articles to a user's personal feed or to publications they contribute to. NOTE: Medium stopped issuing new integration tokens in 2023 — this connector works only for users who already hold a legacy integration token. The API also has no comments endpoint and never has, so reading comments is out of scope.

## Use Cases

- Cross-post blog articles to Medium
- Auto-publish AI-generated drafts
- Publish to publications via API

## Installation

```bash
pip install "toolsconnector[medium]"
```

Set your credentials:

```bash
export TC_MEDIUM_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["medium"], credentials={"medium": "your-token"})

# Get the authenticated Medium user's profile
result = kit.execute("medium_get_me", {})
print(result)
```

### MCP Server

```python
kit = ToolKit(["medium"], credentials={"medium": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["medium"], credentials={"medium": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### Bearer Token (Integration)

1. Medium
2. Settings
3. Integration tokens (LEGACY USERS ONLY — new tokens cannot be obtained)

[Get credentials &rarr;](https://medium.com/me/settings)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("medium_get_me", {})
except RateLimitError as e:
    print(f"Rate limited. Retry in {e.retry_after_seconds}s")
except AuthError as e:
    print(f"Auth failed: {e.suggestion}")
```

## Not Supported

The Medium API has long-standing structural gaps that this connector cannot work around:

| Capability | Why it's not implemented |
|---|---|
| **Read comments** | The Medium REST API has no comments endpoint and never has. There is no public way to enumerate or read article comments. |
| **List user posts** | The Medium REST API exposes no user-posts list endpoint. RSS scraping was rejected (fragile and against the spirit of TOS). |
| **New integration tokens** | Medium stopped issuing new integration tokens in 2023. This connector works only for users who already hold a legacy token. |

If you need these capabilities, no Medium connector — ours or anyone else's — can deliver them via the official API.

## Actions

<!-- ACTIONS_START -->
<!-- This section is auto-generated from the connector spec. Do not edit manually. -->
<!-- ACTIONS_END -->

## Tips

- Rate limit is Undocumented; conservative defaults applied — use pagination and caching to minimize API calls
- Actions marked as destructive (`create_publication_post`, `create_user_post`) cannot be undone — use with caution

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
