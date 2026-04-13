# Segment

> Customer data platform and event tracking

| | |
|---|---|
| **Company** | Twilio (Segment) |
| **Category** | Analytics |
| **Protocol** | REST |
| **Website** | [segment.com](https://segment.com) |
| **API Docs** | [segment.com](https://segment.com/docs/api/) |
| **Auth** | Bearer Token (API Token) |
| **Rate Limit** | 100 requests/second |
| **Pricing** | Free tier, Team from $120/month |

---

## Overview

The Segment API provides access to sources, destinations, tracking events, and user profiles. Collect and route customer data, manage tracking plans, configure destinations, and build unified customer data pipelines.

## Use Cases

- Event tracking
- Customer data routing
- Analytics pipeline management
- Data governance
- User profile unification

## Installation

```bash
pip install toolsconnector[segment]
```

Set your credentials:

```bash
export TC_SEGMENT_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["segment"], credentials={"segment": "your-token"})

# Get a specific destination for a source
result = kit.execute("segment_get_destination", {"source_id": "your-source_id", "destination_id": "your-destination_id"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["segment"], credentials={"segment": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["segment"], credentials={"segment": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### Bearer Token (API Token)

1. Create an account at [Segment](https://segment.com)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://app.segment.com/)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("segment_get_destination", {})
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

- Use batch operations (`batch_identify`, `batch_track`) for bulk operations instead of individual calls
- Rate limit is 100 requests/second — use pagination and caching to minimize API calls
- Actions marked as destructive (`batch_identify`, `batch_track`, `create_source`) cannot be undone — use with caution

## Related Connectors

- [Mixpanel](../mixpanel/) — Product analytics

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
