# AWS Route 53

> Scalable DNS and domain name registration

| | |
|---|---|
| **Company** | Amazon Web Services |
| **Category** | Networking |
| **Protocol** | REST |
| **Website** | [aws.amazon.com/route53](https://aws.amazon.com/route53/) |
| **API Docs** | [docs.aws.amazon.com](https://docs.aws.amazon.com/Route53/latest/APIReference/) |
| **Auth** | AWS SigV4 |
| **Rate Limit** | 5 requests/sec |
| **Pricing** | $0.50/hosted zone/month + $0.40/million queries |

---

## Overview



## Installation

```bash
pip install "toolsconnector[route53]"
```

Set your credentials:

```bash
export TC_ROUTE53_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["route53"], credentials={"route53": "your-token"})

# Get a health check
result = kit.execute("route53_get_health_check", {"health_check_id": "your-health_check_id"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["route53"], credentials={"route53": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["route53"], credentials={"route53": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### AWS SigV4

1. Create an account at [AWS Route 53](https://aws.amazon.com/route53/)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://console.aws.amazon.com/iam/home#/security_credentials)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("route53_get_health_check", {})
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

- Rate limit is 5 requests/sec — use pagination and caching to minimize API calls
- Actions marked as destructive (`delete_health_check`, `delete_hosted_zone`, `delete_record`) cannot be undone — use with caution

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
