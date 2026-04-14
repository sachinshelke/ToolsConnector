# Confluence

> Team wiki, documentation, and knowledge management

| | |
|---|---|
| **Company** | Atlassian |
| **Category** | Knowledge |
| **Protocol** | REST |
| **Website** | [www.atlassian.com/software/confluence](https://www.atlassian.com/software/confluence) |
| **API Docs** | [developer.atlassian.com](https://developer.atlassian.com/cloud/confluence/rest/v2/intro/) |
| **Auth** | Basic Auth (email:api_token), OAuth 2.0 |
| **Rate Limit** | 100 requests/minute |
| **Pricing** | Free up to 10 users, Standard from $6.05/user/month |

---

## Overview

The Confluence REST API provides access to spaces, pages, blog posts, comments, and attachments. Create and organize documentation, search content, manage permissions, and build knowledge management workflows.

## Use Cases

- Documentation automation
- Knowledge base management
- Content publishing
- Team collaboration
- Compliance documentation

## Installation

```bash
pip install "toolsconnector[confluence]"
```

Set your credentials:

```bash
export TC_CONFLUENCE_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["confluence"], credentials={"confluence": "your-token"})

# List pages in a space or across all spaces
result = kit.execute("confluence_list_pages", {"space_id": "space-123", "limit": 25})
print(result)
```

### MCP Server

```python
kit = ToolKit(["confluence"], credentials={"confluence": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["confluence"], credentials={"confluence": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### Basic Auth (email:api_token)

1. Create an account at [Confluence](https://www.atlassian.com/software/confluence)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://id.atlassian.com/manage-profile/security/api-tokens)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("confluence_list_pages", {})
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

- Use `search` for filtered queries and `list_attachments` for paginated browsing
- Rate limit is 100 requests/minute — use pagination and caching to minimize API calls
- Actions marked as destructive (`add_comment`, `add_page_label`, `create_blog_post`) cannot be undone — use with caution
- Use cursor-based pagination for large result sets — pass the `cursor` from previous responses

## Related Connectors

- [Notion](../notion/) — Knowledge workspace

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
