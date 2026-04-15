# AWS CloudWatch

> Monitor AWS resources and applications in real time

| | |
|---|---|
| **Company** | Amazon Web Services |
| **Category** | Devops |
| **Protocol** | REST |
| **Website** | [aws.amazon.com/cloudwatch](https://aws.amazon.com/cloudwatch/) |
| **API Docs** | [docs.aws.amazon.com](https://docs.aws.amazon.com/AmazonCloudWatch/latest/APIReference/) |
| **Auth** | AWS SigV4 |
| **Rate Limit** | 50 requests/sec |
| **Pricing** | Free tier + pay-per-use |

---

## Overview



## Installation

```bash
pip install "toolsconnector[cloudwatch]"
```

Set your credentials:

```bash
export TC_CLOUDWATCH_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["cloudwatch"], credentials={"cloudwatch": "your-token"})

# Get a CloudWatch dashboard
result = kit.execute("cloudwatch_get_dashboard", {"dashboard_name": "your-dashboard_name"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["cloudwatch"], credentials={"cloudwatch": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["cloudwatch"], credentials={"cloudwatch": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### AWS SigV4

1. Create an account at [AWS CloudWatch](https://aws.amazon.com/cloudwatch/)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://console.aws.amazon.com/iam/home#/security_credentials)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("cloudwatch_get_dashboard", {})
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

- Rate limit is 50 requests/sec — use pagination and caching to minimize API calls
- Actions marked as destructive (`delete_alarms`, `delete_dashboards`, `delete_log_group`) cannot be undone — use with caution

## Related Connectors

- [Cloudflare](../cloudflare/) — CDN and security
- [Datadog](../datadog/) — Monitoring
- [Pagerduty](../pagerduty/) — Incident management
- [Vercel](../vercel/) — Frontend deployment

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
