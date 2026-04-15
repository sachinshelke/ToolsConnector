# AWS ECR

> Fully managed container image registry

| | |
|---|---|
| **Company** | Amazon Web Services |
| **Category** | Devops |
| **Protocol** | REST |
| **Website** | [aws.amazon.com/ecr](https://aws.amazon.com/ecr/) |
| **API Docs** | [docs.aws.amazon.com](https://docs.aws.amazon.com/AmazonECR/latest/APIReference/) |
| **Auth** | AWS SigV4 |
| **Rate Limit** | 100 requests/sec |
| **Pricing** | Pay-per-use ($0.10/GB/month) |

---

## Overview



## Installation

```bash
pip install "toolsconnector[ecr]"
```

Set your credentials:

```bash
export TC_ECR_CREDENTIALS=your-token
```

## Quick Start

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["ecr"], credentials={"ecr": "your-token"})

# Get an authorization token for Docker login
result = kit.execute("ecr_get_authorization_token", {})
print(result)
```

### MCP Server

```python
kit = ToolKit(["ecr"], credentials={"ecr": "your-token"})
kit.serve_mcp()  # Claude Desktop / Cursor connects instantly
```

### OpenAI Function Calling

```python
kit = ToolKit(["ecr"], credentials={"ecr": "your-token"})
tools = kit.to_openai_tools()
# Pass to: openai.chat.completions.create(tools=tools, ...)
```

## Authentication

### AWS SigV4

1. Create an account at [AWS ECR](https://aws.amazon.com/ecr/)
2. Navigate to API settings or developer console
3. Generate an API key or access token

[Get credentials &rarr;](https://console.aws.amazon.com/iam/home#/security_credentials)

## Error Handling

```python
from toolsconnector.errors import RateLimitError, AuthError

try:
    result = kit.execute("ecr_get_authorization_token", {})
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

- Use batch operations (`batch_delete_image`) for bulk operations instead of individual calls
- Rate limit is 100 requests/sec — use pagination and caching to minimize API calls
- Actions marked as destructive (`batch_delete_image`, `delete_repository`) cannot be undone — use with caution

## Related Connectors

- [Cloudflare](../cloudflare/) — CDN and security
- [Datadog](../datadog/) — Monitoring
- [Pagerduty](../pagerduty/) — Incident management
- [Vercel](../vercel/) — Frontend deployment

---

*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*
