# HubSpot

> CRM, marketing, sales, and service hub

| | |
|---|---|
| **Company** | HubSpot Inc. |
| **Category** | Crm |
| **Protocol** | REST |
| **Website** | [hubspot.com](https://hubspot.com) |
| **API Docs** | [developers.hubspot.com](https://developers.hubspot.com/docs/api/crm) |
| **Auth** | Bearer Token (Private App), OAuth 2.0 |
| **Rate Limit** | 100 requests/10 seconds (private apps) |
| **Pricing** | Free CRM, Starter from $20/month |

---

## Overview

The HubSpot CRM API provides access to contacts, companies, deals, tickets, and pipelines. Search and filter records, manage sales pipelines, and build marketing automation workflows on HubSpot's platform.

## Use Cases

- Contact management
- Deal pipeline tracking
- Marketing automation
- Customer support ticketing
- Sales analytics

## Installation

```bash
pip install "toolsconnector[hubspot]"
```

Set your credentials:

```bash
export TC_HUBSPOT_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["hubspot"], credentials={"hubspot": "your-token"})

# List contacts
result = kit.execute("hubspot_list_contacts", {"limit": 100, "after": "your-after"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["hubspot"], credentials={"hubspot": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["hubspot"], credentials={"hubspot": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### Bearer Token (Private App)

1. Settings
2. Integrations
3. Private Apps
4. Create

[Get credentials &rarr;](https://app.hubspot.com/settings)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("hubspot_list_contacts", {})
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

- Use `search_contacts` for filtered queries and `list_companies` for paginated browsing
- Rate limit is 100 requests/10 seconds (private apps) — use pagination and caching to minimize API calls
- Actions marked as destructive (`create_company`, `create_contact`, `create_deal`) cannot be undone — use with caution

## Related Connectors

- [Salesforce](../salesforce/) — Enterprise CRM
- [Freshdesk](../freshdesk/) — Helpdesk
- [Intercom](../intercom/) — Customer messaging
- [Zendesk](../zendesk/) — Support ticketing

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
