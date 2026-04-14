# PagerDuty

> Incident management and on-call scheduling

| | |
|---|---|
| **Company** | PagerDuty Inc. |
| **Category** | Devops |
| **Protocol** | REST |
| **Website** | [pagerduty.com](https://pagerduty.com) |
| **API Docs** | [developer.pagerduty.com](https://developer.pagerduty.com/api-reference/) |
| **Auth** | API Key |
| **Rate Limit** | 960 requests/minute |
| **Pricing** | Free up to 5 users, Professional from $21/user/month |

---

## Overview

The PagerDuty API provides access to incidents, services, users, schedules, and escalation policies. Automate incident response, manage on-call rotations, trigger and resolve alerts, and build custom monitoring integrations.

## Use Cases

- Incident management
- On-call scheduling
- Alert automation
- Escalation policy management
- Service health dashboards

## Installation

```bash
pip install "toolsconnector[pagerduty]"
```

Set your credentials:

```bash
export TC_PAGERDUTY_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["pagerduty"], credentials={"pagerduty": "your-token"})

# List PagerDuty users
result = kit.execute("pagerduty_list_users", {"limit": "your-limit"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["pagerduty"], credentials={"pagerduty": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["pagerduty"], credentials={"pagerduty": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### API Key

1. Create an account at [PagerDuty](https://pagerduty.com)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://support.pagerduty.com/main/docs/api-access-keys)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("pagerduty_list_users", {})
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

- Rate limit is 960 requests/minute — use pagination and caching to minimize API calls
- Actions marked as destructive (`acknowledge_incident`, `create_incident`, `create_service`) cannot be undone — use with caution

## Related Connectors

- [Cloudflare](../cloudflare/) — CDN and security
- [Datadog](../datadog/) — Monitoring
- [Vercel](../vercel/) — Frontend deployment
- [Dockerhub](../dockerhub/) — Container registry

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
