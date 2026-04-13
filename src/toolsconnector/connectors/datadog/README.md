# Datadog

> Monitoring, APM, and log management platform

| | |
|---|---|
| **Company** | Datadog Inc. |
| **Category** | Devops |
| **Protocol** | REST |
| **Website** | [datadoghq.com](https://datadoghq.com) |
| **API Docs** | [docs.datadoghq.com](https://docs.datadoghq.com/api/latest/) |
| **Auth** | API Key + Application Key |
| **Rate Limit** | 300 requests/hour for some endpoints |
| **Pricing** | Free tier, Pro from $15/host/month |

---

## Overview

The Datadog API lets you manage dashboards, monitors, metrics, logs, and incidents. Query time-series data, create alerts, manage service catalogs, and build observability automation for your infrastructure.

## Use Cases

- Infrastructure monitoring
- Alert management
- Dashboard automation
- Log analysis
- Incident response

## Installation

```bash
pip install toolsconnector[datadog]
```

Set your credentials:

```bash
export TC_DATADOG_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["datadog"], credentials={"datadog": "your-token"})

# List Datadog events
result = kit.execute("datadog_list_events", {"start": 10, "end": 10, "priority": "your-priority"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["datadog"], credentials={"datadog": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["datadog"], credentials={"datadog": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### API Key + Application Key

1. Create an account at [Datadog](https://datadoghq.com)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://app.datadoghq.com/organization-settings/api-keys)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("datadog_list_events", {})
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

- Use `search_logs` for filtered queries and `list_dashboards` for paginated browsing
- Rate limit is 300 requests/hour for some endpoints — use pagination and caching to minimize API calls
- Actions marked as destructive (`cancel_downtime`, `create_downtime`, `create_event`) cannot be undone — use with caution
- This connector has 22 actions — use `ToolKit(include_actions=[...])` to expose only what your agent needs

## Related Connectors

- [Cloudflare](../cloudflare/) — CDN and security
- [Pagerduty](../pagerduty/) — Incident management
- [Vercel](../vercel/) — Frontend deployment
- [Dockerhub](../dockerhub/) — Container registry

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
