# AWS CloudFront

> Fast, secure content delivery network (CDN)

| | |
|---|---|
| **Company** | Amazon Web Services |
| **Category** | Devops |
| **Protocol** | REST |
| **Website** | [aws.amazon.com/cloudfront](https://aws.amazon.com/cloudfront/) |
| **API Docs** | [docs.aws.amazon.com](https://docs.aws.amazon.com/cloudfront/latest/APIReference/) |
| **Auth** | AWS SigV4 |
| **Rate Limit** | 100 requests/sec |
| **Pricing** | Pay-per-use |

---

## Overview



## Installation

```bash
pip install "toolsconnector[cloudfront]"
```

Set your credentials:

```bash
export TC_CLOUDFRONT_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["cloudfront"], credentials={"cloudfront": "your-token"})

# Get a CloudFront distribution by ID
result = kit.execute("cloudfront_get_distribution", {"distribution_id": "your-distribution_id"})
print(result)
```

### MCP Server

```python
kit = ToolKit(["cloudfront"], credentials={"cloudfront": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["cloudfront"], credentials={"cloudfront": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### AWS SigV4

1. Create an account at [AWS CloudFront](https://aws.amazon.com/cloudfront/)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://console.aws.amazon.com/iam/home#/security_credentials)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("cloudfront_get_distribution", {})
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

- Rate limit is 100 requests/sec — use pagination and caching to minimize API calls
- Actions marked as destructive (`create_distribution`, `delete_distribution`) cannot be undone — use with caution

## Related Connectors

- [Cloudflare](../cloudflare/) — CDN and security
- [Datadog](../datadog/) — Monitoring
- [Pagerduty](../pagerduty/) — Incident management
- [Vercel](../vercel/) — Frontend deployment

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
