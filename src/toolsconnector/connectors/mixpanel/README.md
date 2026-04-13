# Mixpanel

> Product analytics and user behavior tracking

| | |
|---|---|
| **Company** | Mixpanel Inc. |
| **Category** | Analytics |
| **Protocol** | REST |
| **Website** | [mixpanel.com](https://mixpanel.com) |
| **API Docs** | [developer.mixpanel.com](https://developer.mixpanel.com/reference/overview) |
| **Auth** | Service Account (Basic Auth) |
| **Rate Limit** | Varies by endpoint |
| **Pricing** | Free up to 20M events, Growth from $28/month |

---

## Overview

The Mixpanel API lets you track events, query analytics data, manage user profiles, and export data. Build product analytics pipelines, create funnels, analyze user retention, and automate reporting workflows.

## Use Cases

- Event tracking
- Funnel analysis
- User retention reporting
- A/B test analysis
- Data export and ETL

## Installation

```bash
pip install toolsconnector[mixpanel]
```

Set your credentials:

```bash
export TC_MIXPANEL_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["mixpanel"], credentials={"mixpanel": "your-token"})

# Get event count for a date range
result = kit.execute("mixpanel_get_event_count", {"event": "your-event", "from_date": "your-from_date", "to_date": "your-to_date"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["mixpanel"], credentials={"mixpanel": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["mixpanel"], credentials={"mixpanel": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### Service Account (Basic Auth)

1. Create an account at [Mixpanel](https://mixpanel.com)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://mixpanel.com/settings/project#serviceaccounts)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("mixpanel_get_event_count", {})
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

- Rate limit is Varies by endpoint — use pagination and caching to minimize API calls
- Actions marked as destructive (`create_annotation`, `delete_profile`) cannot be undone — use with caution

## Related Connectors

- [Segment](../segment/) — Customer data

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
