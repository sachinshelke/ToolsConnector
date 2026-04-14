# Cloudflare

> CDN, DNS, security, and edge computing platform

| | |
|---|---|
| **Company** | Cloudflare Inc. |
| **Category** | Devops |
| **Protocol** | REST |
| **Website** | [cloudflare.com](https://cloudflare.com) |
| **API Docs** | [developers.cloudflare.com](https://developers.cloudflare.com/api/) |
| **Auth** | API Token, API Key + Email |
| **Rate Limit** | 1,200 requests/5 minutes |
| **Pricing** | Free tier, Pro from $20/month |

---

## Overview

The Cloudflare API provides access to DNS records, zones, firewall rules, Workers, and more. Manage your web infrastructure, configure security policies, deploy serverless functions, and monitor traffic analytics.

## Use Cases

- DNS management
- CDN configuration
- Web security rules
- Edge worker deployment
- Traffic analytics

## Installation

```bash
pip install "toolsconnector[cloudflare]"
```

Set your credentials:

```bash
export TC_CLOUDFLARE_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["cloudflare"], credentials={"cloudflare": "your-token"})

# Get Cloudflare zone analytics
result = kit.execute("cloudflare_get_analytics", {"zone_id": "your-zone_id", "since": "your-since"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["cloudflare"], credentials={"cloudflare": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["cloudflare"], credentials={"cloudflare": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### API Token

1. Create an account at [Cloudflare](https://cloudflare.com)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://dash.cloudflare.com/profile/api-tokens)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("cloudflare_get_analytics", {})
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

- Rate limit is 1,200 requests/5 minutes — use pagination and caching to minimize API calls
- Actions marked as destructive (`create_dns_record`, `create_page_rule`, `create_zone`) cannot be undone — use with caution
- This connector has 23 actions — use `ToolKit(include_actions=[...])` to expose only what your agent needs

## Related Connectors

- [Datadog](../datadog/) — Monitoring
- [Pagerduty](../pagerduty/) — Incident management
- [Vercel](../vercel/) — Frontend deployment
- [Dockerhub](../dockerhub/) — Container registry

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
