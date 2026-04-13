# Salesforce

> CRM, sales, service, and marketing platform

| | |
|---|---|
| **Company** | Salesforce Inc. |
| **Category** | Crm |
| **Protocol** | REST |
| **Website** | [salesforce.com](https://salesforce.com) |
| **API Docs** | [developer.salesforce.com](https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/) |
| **Auth** | OAuth 2.0, Bearer Token |
| **Rate Limit** | Varies by edition |
| **Pricing** | Enterprise pricing (from $25/user/month) |

---

## Overview

The Salesforce REST API provides access to CRM objects including leads, contacts, accounts, opportunities, and cases. Run SOQL queries, manage records, and integrate with the world's most widely-used CRM platform.

## Use Cases

- CRM data sync
- Lead management
- Sales pipeline automation
- Customer support workflows
- Marketing analytics

## Installation

```bash
pip install toolsconnector[salesforce]
```

Set your credentials:

```bash
export TC_SALESFORCE_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["salesforce"], credentials={"salesforce": "your-token"})

# Run a SOSL search
result = kit.execute("salesforce_search", {"sosl": "your-sosl"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["salesforce"], credentials={"salesforce": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["salesforce"], credentials={"salesforce": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### OAuth 2.0

1. Setup
2. Apps
3. App Manager
4. Connected App

[Get credentials &rarr;](https://login.salesforce.com)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("salesforce_search", {})
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

- Use `search` for filtered queries and `list_objects` for paginated browsing
- Rate limit is Varies by edition — use pagination and caching to minimize API calls
- Actions marked as destructive (`create_account`, `create_case`, `create_contact`) cannot be undone — use with caution
- This connector has 21 actions — use `ToolKit(include_actions=[...])` to expose only what your agent needs

## Related Connectors

- [Hubspot](../hubspot/) — Marketing & sales CRM
- [Freshdesk](../freshdesk/) — Helpdesk
- [Intercom](../intercom/) — Customer messaging
- [Zendesk](../zendesk/) — Support ticketing

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
