# Intercom

> Customer messaging and engagement platform

| | |
|---|---|
| **Company** | Intercom Inc. |
| **Category** | Crm |
| **Protocol** | REST |
| **Website** | [intercom.com](https://intercom.com) |
| **API Docs** | [developers.intercom.com](https://developers.intercom.com/docs/references/rest-api/api.intercom.io/) |
| **Auth** | Bearer Token (Access Token) |
| **Rate Limit** | Varies by plan and endpoint |
| **Pricing** | From $39/seat/month |

---

## Overview

The Intercom API provides access to contacts, conversations, articles, teams, and tags. Manage customer communication, automate messaging workflows, build help center content, and integrate with your CRM.

## Use Cases

- Customer communication
- In-app messaging
- Help center management
- Lead qualification
- User engagement tracking

## Installation

```bash
pip install toolsconnector[intercom]
```

Set your credentials:

```bash
export TC_INTERCOM_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["intercom"], credentials={"intercom": "your-token"})

# List contacts
result = kit.execute("intercom_list_contacts", {"limit": 50, "starting_after": "your-starting_after"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["intercom"], credentials={"intercom": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["intercom"], credentials={"intercom": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### Bearer Token (Access Token)

1. Create an account at [Intercom](https://intercom.com)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://app.intercom.com/a/apps/_/developer-hub)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("intercom_list_contacts", {})
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

- Use `search_contacts` for filtered queries and `list_admins` for paginated browsing
- Rate limit is Varies by plan and endpoint — use pagination and caching to minimize API calls
- Actions marked as destructive (`create_contact`, `create_message`, `create_note`) cannot be undone — use with caution

## Related Connectors

- [Salesforce](../salesforce/) — Enterprise CRM
- [Hubspot](../hubspot/) — Marketing & sales CRM
- [Freshdesk](../freshdesk/) — Helpdesk
- [Zendesk](../zendesk/) — Support ticketing

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
