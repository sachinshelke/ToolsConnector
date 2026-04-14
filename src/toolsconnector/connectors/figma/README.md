# Figma

> Collaborative design and prototyping tool

| | |
|---|---|
| **Company** | Figma Inc. (Adobe) |
| **Category** | Productivity |
| **Protocol** | REST |
| **Website** | [figma.com](https://figma.com) |
| **API Docs** | [www.figma.com](https://www.figma.com/developers/api) |
| **Auth** | Personal Access Token, OAuth 2.0 |
| **Rate Limit** | 30 requests/minute per token |
| **Pricing** | Free tier, Professional from $15/editor/month |

---

## Overview

The Figma API provides access to files, components, styles, comments, and project metadata. Extract design tokens, automate asset export, manage team libraries, and build design-to-code workflows.

## Use Cases

- Design token extraction
- Automated asset export
- Design system management
- Comment and review automation
- Design analytics

## Installation

```bash
pip install "toolsconnector[figma]"
```

Set your credentials:

```bash
export TC_FIGMA_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["figma"], credentials={"figma": "your-token"})

# List projects for a Figma team
result = kit.execute("figma_list_projects", {"team_id": "T01234567"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["figma"], credentials={"figma": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["figma"], credentials={"figma": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### Personal Access Token

1. Create an account at [Figma](https://figma.com)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://www.figma.com/developers/api#access-tokens)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("figma_list_projects", {})
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

- Rate limit is 30 requests/minute per token — use pagination and caching to minimize API calls
- Actions marked as destructive (`create_webhook`, `delete_comment`, `delete_webhook`) cannot be undone — use with caution
- Use cursor-based pagination for large result sets — pass the `cursor` from previous responses
- This connector has 22 actions — use `ToolKit(include_actions=[...])` to expose only what your agent needs

## Related Connectors

- [Gcalendar](../gcalendar/) — Calendar
- [Gdocs](../gdocs/) — Documents
- [Gsheets](../gsheets/) — Spreadsheets
- [Gtasks](../gtasks/) — Task lists

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
