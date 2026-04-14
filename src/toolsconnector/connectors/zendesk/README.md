# Zendesk

> Customer service and support ticketing platform

| | |
|---|---|
| **Company** | Zendesk Inc. |
| **Category** | Crm |
| **Protocol** | REST |
| **Website** | [zendesk.com](https://zendesk.com) |
| **API Docs** | [developer.zendesk.com](https://developer.zendesk.com/api-reference/) |
| **Auth** | API Token, OAuth 2.0 |
| **Rate Limit** | 400 requests/minute |
| **Pricing** | Suite Team from $55/agent/month |

---

## Overview

The Zendesk API provides access to tickets, users, organizations, and help center articles. Manage support workflows, automate ticket routing, track satisfaction scores, and build custom customer service integrations.

## Use Cases

- Ticket management
- Customer support automation
- Help center content
- Satisfaction tracking
- Multi-channel support

## Installation

```bash
pip install "toolsconnector[zendesk]"
```

Set your credentials:

```bash
export TC_ZENDESK_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["zendesk"], credentials={"zendesk": "your-token"})

# List tickets from Zendesk
result = kit.execute("zendesk_list_tickets", {"status": "active", "limit": 25})
print(result)
```

### MCP Server

```python
kit = ToolKit(["zendesk"], credentials={"zendesk": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["zendesk"], credentials={"zendesk": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### API Token

1. Create an account at [Zendesk](https://zendesk.com)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://developer.zendesk.com/documentation/ticketing/getting-started/getting-a-token/)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("zendesk_list_tickets", {})
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

- Use `search` for filtered queries and `list_groups` for paginated browsing
- Rate limit is 400 requests/minute — use pagination and caching to minimize API calls
- Actions marked as destructive (`add_comment`, `create_ticket`, `create_user`) cannot be undone — use with caution

## Related Connectors

- [Salesforce](../salesforce/) — Enterprise CRM
- [Hubspot](../hubspot/) — Marketing & sales CRM
- [Freshdesk](../freshdesk/) — Helpdesk
- [Intercom](../intercom/) — Customer messaging

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
